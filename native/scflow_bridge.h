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

/* 释放全部已加载模块。 */
SCF_API void scf_finalize(void);

#ifdef __cplusplus
}
#endif
