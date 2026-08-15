#!/usr/bin/env python3
# pskernel_v37 的完整签名补全表（V36/V37 新增 104 个 PK_* 导出）

# 置信度：high = 文档化同族签名 + 反汇编 argc/byte 吻合 +（部分）经验调用；
#         med  = 家族约定 + 反汇编 argc；low = 仅命名约定 + argc。
# 依据缩写：V35 = V35 手册同族；DIS = 反汇编 argc/字节参数；PROBE = 经验调用；
#           SCH = sch_37102 节点类型；NOM = 命名约定。

V37_BASE_SIGNATURES = {
    "PK_ASSEMBLY_check": "PK_ERROR_code_t PK_ASSEMBLY_check(int n_assemblies, const PK_ASSEMBLY_t assemblies[], const PK_ASSEMBLY_check_o_t *options, PK_TOPOL_track_r_t *const tracking, PK_ASSEMBLY_check_r_t *const results)",
    "PK_BODY_ask_frames": "PK_ERROR_code_t PK_BODY_ask_frames(PK_BODY_t body, int *const n_frames, PK_FRAME_t **const frames)",
    "PK_BODY_create_implicit": "PK_ERROR_code_t PK_BODY_create_implicit(const PK_BODY_create_implicit_o_t *options, PK_BODY_t *const body)",
    "PK_BODY_enlarge": "PK_ERROR_code_t PK_BODY_enlarge(int n_bodies, const PK_BODY_t bodies[], const PK_BODY_enlarge_o_t *options, PK_BODY_enlarge_r_t *const results)",
    "PK_BODY_is_cellular": "PK_ERROR_code_t PK_BODY_is_cellular(PK_BODY_t body, PK_LOGICAL_t *const is_cellular)",
    "PK_BODY_is_disjoint": "PK_ERROR_code_t PK_BODY_is_disjoint(int n_bodies, const PK_BODY_t bodies[], PK_LOGICAL_t *const is_disjoint)",
    "PK_BODY_make_patterned": "PK_ERROR_code_t PK_BODY_make_patterned(int n_bodies, const PK_BODY_t bodies[], const PK_BODY_make_patterned_o_t *options, PK_BODY_make_patterned_r_t *const results)",
    "PK_BODY_slice": "PK_ERROR_code_t PK_BODY_slice(PK_BODY_t body, PK_LOGICAL_t keep_both_sides, const PK_BODY_slice_o_t *options, PK_BODY_t *const results)",
    "PK_FACE_ask_type": "PK_ERROR_code_t PK_FACE_ask_type(PK_FACE_t face, PK_FACE_type_t *const type)",
    "PK_FACE_identify_blends_2": "PK_ERROR_code_t PK_FACE_identify_blends_2(int n_faces, const PK_FACE_t faces[], const PK_FACE_identify_blends_o_t *options, PK_FACE_identify_blends_r_t *const results)",
    "PK_FACE_pattern_2": "PK_ERROR_code_t PK_FACE_pattern_2(int n_pattern_faces, const PK_FACE_t pattern_faces[], int n_transforms, const PK_TRANSF_t transforms[], const PK_FACE_pattern_o_t *options, PK_FACE_pattern_r_t *const pattern_results)",
    "PK_FRAME_ask_body": "PK_ERROR_code_t PK_FRAME_ask_body(PK_FRAME_t frame, PK_BODY_t *const body)",
    "PK_FRAME_ask_geometry": "PK_ERROR_code_t PK_FRAME_ask_geometry(PK_FRAME_t frame, PK_GEOM_t *const geometry)",
    "PK_FRAME_ask_owner": "PK_ERROR_code_t PK_FRAME_ask_owner(PK_FRAME_t frame, PK_TOPOL_t *const owner)",
    "PK_FRAME_ask_sense": "PK_ERROR_code_t PK_FRAME_ask_sense(PK_FRAME_t frame, PK_LOGICAL_t *const sense)",
    "PK_FRAME_attach_geoms": "PK_ERROR_code_t PK_FRAME_attach_geoms(PK_FRAME_t frame, int n_geoms, const PK_GEOM_t geoms[], PK_LOGICAL_t *const attached)",
    "PK_FRAME_reverse": "PK_ERROR_code_t PK_FRAME_reverse(PK_FRAME_t frame)",
    "PK_GEOM_enlarge": "PK_ERROR_code_t PK_GEOM_enlarge(PK_GEOM_t geom, const PK_GEOM_enlarge_o_t *options)",
    "PK_LATTICE_ask_bound": "PK_ERROR_code_t PK_LATTICE_ask_bound(PK_LATTICE_t lattice, PK_TOPOL_t *const bound)",
    "PK_LATTICE_ask_cell": "PK_ERROR_code_t PK_LATTICE_ask_cell(PK_LATTICE_t lattice, PK_TOPOL_t *const cell)",
    "PK_LATTICE_ask_connectivity": "PK_ERROR_code_t PK_LATTICE_ask_connectivity(PK_LATTICE_t lattice, int *const n_links, PK_LATTICE_link_t **const links)",
    "PK_LATTICE_ask_core": "PK_ERROR_code_t PK_LATTICE_ask_core(PK_LATTICE_t lattice, PK_GEOM_t *const core)",
    "PK_LATTICE_ask_form": "PK_ERROR_code_t PK_LATTICE_ask_form(PK_LATTICE_t lattice, PK_LATTICE_form_t *const form)",
    "PK_LATTICE_ask_regions": "PK_ERROR_code_t PK_LATTICE_ask_regions(PK_LATTICE_t lattice, int *const n_regions, PK_REGION_t **const regions)",
    "PK_LATTICE_ask_type": "PK_ERROR_code_t PK_LATTICE_ask_type(PK_LATTICE_t lattice, PK_LATTICE_type_t *const type)",
    "PK_LATTICE_combine": "PK_ERROR_code_t PK_LATTICE_combine(int n_lattices, const PK_LATTICE_t lattices[], const PK_LATTICE_combine_o_t *options, PK_LATTICE_t *const combined)",
    "PK_LATTICE_create_by_core": "PK_ERROR_code_t PK_LATTICE_create_by_core(const PK_LATTICE_create_by_core_o_t *options, PK_LATTICE_t *const lattice)",
    "PK_LATTICE_disjoin": "PK_ERROR_code_t PK_LATTICE_disjoin(PK_LATTICE_t lattice, const PK_LATTICE_disjoin_o_t *options, PK_LATTICE_t *const results)",
    "PK_LATTICE_find_nabox": "PK_ERROR_code_t PK_LATTICE_find_nabox(PK_LATTICE_t lattice, int *const n_naboxes, PK_LATTICE_nabox_t **const naboxes)",
    "PK_LATTICE_make_patterned": "PK_ERROR_code_t PK_LATTICE_make_patterned(int n_lattices, const PK_LATTICE_t lattices[], const PK_LATTICE_make_patterned_o_t *options, PK_LATTICE_make_patterned_r_t *const results)",
    "PK_LATTICE_offset": "PK_ERROR_code_t PK_LATTICE_offset(PK_LATTICE_t lattice, const PK_LATTICE_offset_o_t *options, PK_LATTICE_t *const offset)",
    "PK_LBALL_ask_blend": "PK_ERROR_code_t PK_LBALL_ask_blend(PK_LBALL_t lball, PK_GEOM_t *const blend)",
    "PK_MARK_create_2": "PK_ERROR_code_t PK_MARK_create_2(int n_topols, const PK_TOPOL_t topols[], const PK_MARK_create_o_t *options, PK_MARK_t *const marks)",
    "PK_MARK_delete_2": "PK_ERROR_code_t PK_MARK_delete_2(int n_marks, const PK_MARK_t marks[], const PK_MARK_delete_o_t *options)",
    "PK_PARTITION_ask": "PK_ERROR_code_t PK_PARTITION_ask(PK_PARTITION_t partition, PK_PARTITION_ask_o_t *const options)",
    "PK_PARTITION_ask_pmarks_2": "PK_ERROR_code_t PK_PARTITION_ask_pmarks_2(PK_PARTITION_t partition, int *const n_pmarks, PK_PMARK_t **const pmarks)",
    "PK_PARTITION_clear_guard": "PK_ERROR_code_t PK_PARTITION_clear_guard(PK_PARTITION_t partition)",
    "PK_PARTITION_create": "PK_ERROR_code_t PK_PARTITION_create(PK_BODY_t body, PK_PARTITION_t *const partition)",
    "PK_PARTITION_goto_guard": "PK_ERROR_code_t PK_PARTITION_goto_guard(PK_PARTITION_t partition, PK_PARTITION_t *const guard)",
    "PK_PARTITION_has_guard": "PK_ERROR_code_t PK_PARTITION_has_guard(PK_PARTITION_t partition, PK_LOGICAL_t *const has_guard)",
    "PK_PARTITION_has_lattices": "PK_ERROR_code_t PK_PARTITION_has_lattices(PK_PARTITION_t partition, PK_LOGICAL_t *const has_lattices)",
    "PK_PARTITION_set_guard": "PK_ERROR_code_t PK_PARTITION_set_guard(PK_PARTITION_t partition, PK_PARTITION_t guard)",
    "PK_REGION_ask_lattices": "PK_ERROR_code_t PK_REGION_ask_lattices(PK_REGION_t region, int *const n_lattices, PK_LATTICE_t **const lattices)",
    "PK_REGION_ask_type": "PK_ERROR_code_t PK_REGION_ask_type(PK_REGION_t region, PK_REGION_type_t *const type)",
    "PK_REGION_embed_body": "PK_ERROR_code_t PK_REGION_embed_body(PK_REGION_t region, PK_BODY_t body)",
    "PK_REGION_embed_lattices": "PK_ERROR_code_t PK_REGION_embed_lattices(PK_REGION_t region, int n_lattices, const PK_LATTICE_t lattices[])",
    "PK_REGION_remove_lattice": "PK_ERROR_code_t PK_REGION_remove_lattice(PK_REGION_t region, PK_LATTICE_t lattice)",
    "PK_SESSION_ask_cellular_guise": "PK_ERROR_code_t PK_SESSION_ask_cellular_guise(PK_LOGICAL_t *const cellular_guise)",
    "PK_SESSION_set_cellular_guise": "PK_ERROR_code_t PK_SESSION_set_cellular_guise(PK_LOGICAL_t cellular_guise)",
    "PK_TOPOL_find_connected": "PK_ERROR_code_t PK_TOPOL_find_connected(PK_TOPOL_t topol, int *const n_connected, PK_TOPOL_t **const connected)",
    "PK_TOPOL_find_frames": "PK_ERROR_code_t PK_TOPOL_find_frames(PK_TOPOL_t topol, int *const n_frames, PK_FRAME_t **const frames)",
    "PK_TOPOL_imprint_frames": "PK_ERROR_code_t PK_TOPOL_imprint_frames(PK_TOPOL_t topol, int n_frames, const PK_FRAME_t frames[])",
    "PK_TOPOL_is_connected": "PK_ERROR_code_t PK_TOPOL_is_connected(PK_TOPOL_t topol_1, PK_TOPOL_t topol_2, PK_LOGICAL_t *const is_connected)",
    "PK_TOPOL_render_volume": "PK_ERROR_code_t PK_TOPOL_render_volume(PK_TOPOL_t topol, const PK_TOPOL_render_volume_o_t *options, PK_TOPOL_render_volume_r_t *const results)",
    "PK_TRANSF_enlarge": "PK_ERROR_code_t PK_TRANSF_enlarge(PK_TRANSF_t transf, const PK_TRANSF_enlarge_o_t *options)",
}


def _meta(conf, *basis):
    return {"confidence": conf, "basis": list(basis)}


V37_SIGNATURE_META = {
    "PK_FACE_ask_type": _meta("high", "V35 ask 家族", "DIS argc=2", "PROBE rc=5022 guise"),
    "PK_REGION_ask_type": _meta("high", "V35 ask 家族", "DIS argc=2", "PROBE rc=5022 guise"),
    "PK_REGION_ask_lattices": _meta("high", "V35 ask 家族", "DIS argc=2/3", "PROBE rc=5022 guise"),
    "PK_SESSION_ask_cellular_guise": _meta("high", "PROBE rc=0 (guise=27110)"),
    "PK_LATTICE_ask_type": _meta("high", "DIS 薄 getter [rcx]=tag", "SCH LATTICE"),
    "PK_LATTICE_ask_form": _meta("med", "DIS argc=1", "SCH LATTICE"),
    "PK_LATTICE_ask_bound": _meta("med", "V35 ask 家族", "DIS argc=2"),
    "PK_LATTICE_ask_cell": _meta("med", "V35 ask 家族"),
    "PK_LATTICE_ask_core": _meta("med", "V35 ask 家族"),
    "PK_LATTICE_ask_connectivity": _meta("med", "V35 ask 家族"),
    "PK_LATTICE_ask_regions": _meta("med", "V35 ask 家族", "DIS argc=2"),
    "PK_LATTICE_find_nabox": _meta("med", "V35 ask 家族", "DIS argc=2"),
    "PK_FRAME_ask_body": _meta("high", "V35 ask 家族", "DIS argc=2"),
    "PK_FRAME_ask_geometry": _meta("high", "V35 ask 家族", "DIS argc=2"),
    "PK_FRAME_ask_owner": _meta("med", "V35 ask 家族", "DIS argc=3"),
    "PK_FRAME_ask_sense": _meta("med", "V35 ask 家族", "DIS argc=3"),
    "PK_BODY_ask_frames": _meta("med", "V35 ask 家族", "DIS argc=2"),
    "PK_LBALL_ask_blend": _meta("med", "V35 ask 家族"),
    "PK_PARTITION_ask_pmarks_2": _meta("med", "V35 ask 家族"),
    "PK_PARTITION_has_guard": _meta("med", "V35 is/has 家族"),
    "PK_PARTITION_has_lattices": _meta("med", "V35 is/has 家族"),
    "PK_TOPOL_is_connected": _meta("med", "V35 is/has 家族"),
    "PK_TOPOL_find_connected": _meta("med", "V35 find 家族"),
    "PK_TOPOL_find_frames": _meta("med", "V35 find 家族"),
    "PK_BODY_is_cellular": _meta("med", "V35 is/has 家族", "DIS"),
    "PK_BODY_is_disjoint": _meta("med", "V35 is/has 家族", "DIS"),
    "PK_BODY_slice": _meta("high", "DIS argc=4 且第 2 参 = logical 字节"),
    "PK_BODY_create_implicit": _meta("med", "DIS argc=4", "SCH IMPLICIT_SURF/VOLUME"),
    "PK_BODY_enlarge": _meta("med", "DIS argc=4", "NOM enlarge 家族"),
    "PK_BODY_make_patterned": _meta("med", "DIS argc=3", "SCH PATTERN_*"),
    "PK_FACE_identify_blends_2": _meta("med", "V35 identify_blends 同族", "DIS argc=4"),
    "PK_FACE_pattern_2": _meta("med", "V35 FACE_pattern 同族 + 2", "DIS argc=6"),
    "PK_FRAME_attach_geoms": _meta("med", "DIS argc=2/6", "SCH FRAME"),
    "PK_FRAME_reverse": _meta("med", "NOM", "DIS"),
    "PK_GEOM_enlarge": _meta("med", "DIS argc=1", "NOM enlarge 家族"),
    "PK_LATTICE_combine": _meta("med", "DIS argc=1/4", "SCH LATTICE"),
    "PK_LATTICE_create_by_core": _meta("med", "DIS argc=10(栈参多)", "SCH LATTICE"),
    "PK_LATTICE_disjoin": _meta("med", "DIS argc=1", "SCH LATTICE"),
    "PK_LATTICE_make_patterned": _meta("med", "DIS argc=1", "SCH PATTERN_*"),
    "PK_LATTICE_offset": _meta("med", "DIS argc=6", "SCH LATTICE"),
    "PK_MARK_create_2": _meta("med", "V35 MARK_create 同族 + 2"),
    "PK_MARK_delete_2": _meta("med", "V35 MARK_delete 同族 + 2"),
    "PK_PARTITION_create": _meta("med", "NOM", "SCH PARTITION"),
    "PK_PARTITION_ask": _meta("med", "V35 ask 家族"),
    "PK_PARTITION_clear_guard": _meta("med", "NOM"),
    "PK_PARTITION_goto_guard": _meta("med", "NOM"),
    "PK_PARTITION_set_guard": _meta("med", "NOM"),
    "PK_REGION_embed_body": _meta("med", "NOM", "SCH REGION"),
    "PK_REGION_embed_lattices": _meta("med", "NOM", "SCH REGION"),
    "PK_REGION_remove_lattice": _meta("med", "NOM", "SCH REGION"),
    "PK_SESSION_set_cellular_guise": _meta("med", "对偶 ask_cellular_guise（PROBE 已证 ask）"),
    "PK_TOPOL_imprint_frames": _meta("med", "NOM", "SCH FRAME"),
    "PK_TOPOL_render_volume": _meta("med", "NOM", "DIS"),
    "PK_TRANSF_enlarge": _meta("med", "NOM enlarge 家族"),
    "PK_ASSEMBLY_check": _meta("med", "DIS argc=4", "V35 ASSEMBLY_* 家族"),
}


def build_v37_signatures() -> dict:
    """组装 104 个导出的完整签名表：{name: {proto, confidence, basis}}。"""
    import pskernel_v37 as self_mod
    only = self_mod.v37_only_exports()
    out = {}
    for name in only:
        base = self_mod.base_name(name)
        base_sig = V37_BASE_SIGNATURES.get(base)
        if base_sig is None and name.endswith("_r_f"):
            # PK_MARK_create_r_f -> 基函数 = PK_MARK_create_2（r_f 命名去掉 _2）
            base_sig = V37_BASE_SIGNATURES.get(base + "_2")
            if base_sig is not None:
                base = base + "_2"
        if base_sig is None:
            base_sig = V37_BASE_SIGNATURES.get(name)
        if base_sig is None:
            out[name] = {"proto": None, "confidence": "low",
                         "basis": ["未策展"]}
            continue
        proto = base_sig
        meta = V37_SIGNATURE_META.get(base, V37_SIGNATURE_META.get(name, {}))
        conf = meta.get("confidence", "low")
        basis = list(meta.get("basis", []))
        if name != base:
            head, _, tail = proto.rpartition(")")
            inner = tail.rstrip(" ")
            if name.endswith("_cb_r_f"):
                inner = (inner + ", PK_FRUSTUM_t *frustrum, "
                         "PK_FRUSTUM_t *frustrum_cb, "
                         "PK_TOPOL_track_r_t *const tracking")
            else:
                inner = inner + ", PK_FRUSTUM_t *frustrum"
            proto = head + inner + ")"
            basis = ["基函数 " + base + " 签名"] + basis +                 ["_r_f 约定 = 基参数 + frustrum"]
            if conf != "high":
                conf = "med"
        out[name] = {"proto": proto, "confidence": conf, "basis": basis}
    return out


def dump_signatures_md(path=None) -> str:
    """把完整签名表渲染为 Markdown（可写文件）。"""
    sigs = build_v37_signatures()
    from collections import Counter
    confs = Counter(v["confidence"] for v in sigs.values())
    lines = ["# pskernel V37 新增导出签名补全表",
             "",
             f"> {len(sigs)} 个 V36/V37 新增 PK_* 导出（V35 手册未收录）的"
             f" 最佳努力签名。置信度 {dict(confs)}。",
             "",
             "> 依据：V35 = V35 手册同族签名；DIS = 反汇编参数/字节参数；",
             "> PROBE = 经验调用实测；SCH = sch_37102 节点类型；NOM = 命名约定。",
             "",
             "| 导出 | 签名 | 置信度 | 依据 |",
             "|------|------|--------|------|"]
    for name in sorted(sigs):
        v = sigs[name]
        proto = v["proto"] or "（未策展）"
        basis = ", ".join(v["basis"]) or "-"
        lines.append(f"| {name} | {proto} | {v['confidence']} | {basis} |")
    text = "\n".join(lines) + "\n"
    if path:
        import pathlib
        pathlib.Path(path).write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else None
    print(dump_signatures_md(p))
