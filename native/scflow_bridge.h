/*
 * scflow_bridge.h — C ABI 接口（M2 NativeBridge 原型）
 *
 * 用途：在 MSVC 进程中安全加载 scFLOWpre 的 C++ 导出 DLL（scFLOWpreCmd /
 * SCTprime / SCTpreLib / ParasolidGW），并以 C 接口暴露给 Python ctypes。
 * 当前原型只做“加载 + 符号解析 + 状态汇总”，后续在此之上扩展
 * doc_open/save、shapegroup_create/mdl_create、wrap_execute 等管线 API。
 */
#pragma once

#ifdef __cplusplus
extern "C" {
#endif

#if defined(_WIN32) && defined(SCF_BRIDGE_BUILD)
#  define SCF_API __declspec(dllexport)
#else
#  define SCF_API __declspec(dllimport)
#endif

/*
 * 加载 programs_dir 下的关键 DLL。
 * 返回已成功加载的数量；-1 表示目录无效。
 */
SCF_API int scf_initialize(const wchar_t* programs_dir);

/*
 * 在已加载的模块中解析符号。
 * 返回 1 成功，0 失败，-1 参数错误。
 */
SCF_API int scf_resolve_symbol(const wchar_t* dll_name, const char* symbol);

/*
 * 写出状态摘要（每行一个模块：名称 = 已加载/符号命中数）。
 * 返回写入字符数（不含结尾 NUL）。
 */
SCF_API int scf_status(wchar_t* buffer, int buffer_len);

/*
 * Preprocessing pipeline symbol probe: outputs "module|symbol=1/0" per line.
 * Returns the number of wide chars written (excluding trailing NUL).
 */
SCF_API int scf_pipeline_probe(wchar_t* buffer, int buffer_len);

/*
 * Actually call ZipLibrary ?ExpandZip@@YAHPEB_W0@Z.
 * Returns the callee's return value, or -2 when the symbol is unresolved.
 */
SCF_API int scf_call_zip_expand(const wchar_t* zip_path,
                                const wchar_t* out_dir);

/*
 * SCTprime pipeline ABI helpers.
 *
 * The interface wrappers (IShapeGroupSet / IShapeGroup / ISNode) are all
 * 16-byte MSVC objects: { void* ptr; int id; } (8 + 4 + 4 padding).
 * CreateShapeGroupSet is __cdecl with a hidden sret pointer (RCX) and the
 * name in RDX. CreateShapeGroup is a member function with this in RCX,
 * hidden sret in RDX, name in R8 and the std::vector<ISNode>& in R9.
 *
 * The caller owns the 16-byte output buffers; pass their addresses as
 * handles to later calls. Handles stay valid as long as the buffers live.
 */
#define SCF_ERR_OK                0
#define SCF_ERR_ARG              (-1)
#define SCF_ERR_CONTEXT_NOT_READY (-100)
#define SCF_ERR_EXCEPTION         (-101)
#define SCF_ERR_SYMBOL            (-102)
#define SCF_ERR_NULL_OBJECT       (-103)

/*
 * Returns 1 when the SCTprime host context (document manager at
 * [ctx+0xF8]) is present, 0 when not, -1 when SCTprime is not loaded.
 */
SCF_API int scf_pipeline_context_ready(void);

/*
 * Calls SCTprime::CreateShapeGroupSet(name) and writes the 16-byte
 * IShapeGroupSet wrapper into out_obj. Returns 1 on success, 0 on failure
 * with *err set to one of the SCF_ERR_* codes.
 */
SCF_API int scf_pipeline_create_shape_group_set(const wchar_t* name,
                                                void* out_obj, int* err);

/*
 * Calls IShapeGroupSet::CreateShapeGroup(name, empty vector<ISNode>) with
 * set_handle as `this` and writes the 16-byte IShapeGroup wrapper into
 * out_obj. Returns 1 on success, 0 on failure with *err set.
 */
SCF_API int scf_pipeline_create_shape_group(unsigned __int64 set_handle,
                                            const wchar_t* name,
                                            void* out_obj, int* err);

/*
 * Calls IShapeGroup::CreateMDL() with group_handle as `this`.
 * Returns 1 on success (even when the callee returns false), 0 on failure.
 */
SCF_API int scf_pipeline_create_mdl(unsigned __int64 group_handle,
                                    int* ok, int* err);


/* 释放全部已加载模块。 */
SCF_API void scf_finalize(void);

#ifdef __cplusplus
}
#endif
