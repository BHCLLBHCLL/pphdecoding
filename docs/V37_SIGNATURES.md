# pskernel V37 新增导出签名补全表

> 104 个 V36/V37 新增 PK_* 导出（V35 手册未收录）的 最佳努力签名。置信度 {'med': 89, 'high': 15}。

> 依据：V35 = V35 手册同族签名；DIS = 反汇编参数/字节参数；
> PROBE = 经验调用实测；SCH = sch_37102 节点类型；NOM = 命名约定。

| 导出 | 签名 | 置信度 | 依据 |
|------|------|--------|------|
| PK_ASSEMBLY_check | PK_ERROR_code_t PK_ASSEMBLY_check(int n_assemblies, const PK_ASSEMBLY_t assemblies[], const PK_ASSEMBLY_check_o_t *options, PK_TOPOL_track_r_t *const tracking, PK_ASSEMBLY_check_r_t *const results) | med | DIS argc=4, V35 ASSEMBLY_* 家族 |
| PK_ASSEMBLY_check_r_f | PK_ERROR_code_t PK_ASSEMBLY_check(int n_assemblies, const PK_ASSEMBLY_t assemblies[], const PK_ASSEMBLY_check_o_t *options, PK_TOPOL_track_r_t *const tracking, PK_ASSEMBLY_check_r_t *const results, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_ASSEMBLY_check 签名, DIS argc=4, V35 ASSEMBLY_* 家族, _r_f 约定 = 基参数 + frustrum |
| PK_BODY_ask_frames | PK_ERROR_code_t PK_BODY_ask_frames(PK_BODY_t body, int *const n_frames, PK_FRAME_t **const frames) | med | V35 ask 家族, DIS argc=2 |
| PK_BODY_create_implicit | PK_ERROR_code_t PK_BODY_create_implicit(const PK_BODY_create_implicit_o_t *options, PK_BODY_t *const body) | med | DIS argc=4, SCH IMPLICIT_SURF/VOLUME |
| PK_BODY_create_implicit_r_f | PK_ERROR_code_t PK_BODY_create_implicit(const PK_BODY_create_implicit_o_t *options, PK_BODY_t *const body, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_BODY_create_implicit 签名, DIS argc=4, SCH IMPLICIT_SURF/VOLUME, _r_f 约定 = 基参数 + frustrum |
| PK_BODY_enlarge | PK_ERROR_code_t PK_BODY_enlarge(int n_bodies, const PK_BODY_t bodies[], const PK_BODY_enlarge_o_t *options, PK_BODY_enlarge_r_t *const results) | med | DIS argc=4, NOM enlarge 家族 |
| PK_BODY_enlarge_r_f | PK_ERROR_code_t PK_BODY_enlarge(int n_bodies, const PK_BODY_t bodies[], const PK_BODY_enlarge_o_t *options, PK_BODY_enlarge_r_t *const results, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_BODY_enlarge 签名, DIS argc=4, NOM enlarge 家族, _r_f 约定 = 基参数 + frustrum |
| PK_BODY_is_cellular | PK_ERROR_code_t PK_BODY_is_cellular(PK_BODY_t body, PK_LOGICAL_t *const is_cellular) | med | V35 is/has 家族, DIS |
| PK_BODY_is_cellular_r_f | PK_ERROR_code_t PK_BODY_is_cellular(PK_BODY_t body, PK_LOGICAL_t *const is_cellular, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_BODY_is_cellular 签名, V35 is/has 家族, DIS, _r_f 约定 = 基参数 + frustrum |
| PK_BODY_is_disjoint | PK_ERROR_code_t PK_BODY_is_disjoint(int n_bodies, const PK_BODY_t bodies[], PK_LOGICAL_t *const is_disjoint) | med | V35 is/has 家族, DIS |
| PK_BODY_is_disjoint_r_f | PK_ERROR_code_t PK_BODY_is_disjoint(int n_bodies, const PK_BODY_t bodies[], PK_LOGICAL_t *const is_disjoint, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_BODY_is_disjoint 签名, V35 is/has 家族, DIS, _r_f 约定 = 基参数 + frustrum |
| PK_BODY_make_patterned | PK_ERROR_code_t PK_BODY_make_patterned(int n_bodies, const PK_BODY_t bodies[], const PK_BODY_make_patterned_o_t *options, PK_BODY_make_patterned_r_t *const results) | med | DIS argc=3, SCH PATTERN_* |
| PK_BODY_make_patterned_r_f | PK_ERROR_code_t PK_BODY_make_patterned(int n_bodies, const PK_BODY_t bodies[], const PK_BODY_make_patterned_o_t *options, PK_BODY_make_patterned_r_t *const results, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_BODY_make_patterned 签名, DIS argc=3, SCH PATTERN_*, _r_f 约定 = 基参数 + frustrum |
| PK_BODY_slice | PK_ERROR_code_t PK_BODY_slice(PK_BODY_t body, PK_LOGICAL_t keep_both_sides, const PK_BODY_slice_o_t *options, PK_BODY_t *const results) | high | DIS argc=4 且第 2 参 = logical 字节 |
| PK_BODY_slice_cb_r_f | PK_ERROR_code_t PK_BODY_slice(PK_BODY_t body, PK_LOGICAL_t keep_both_sides, const PK_BODY_slice_o_t *options, PK_BODY_t *const results, PK_FRUSTUM_t *frustrum, PK_FRUSTUM_t *frustrum_cb, PK_TOPOL_track_r_t *const tracking) | high | 基函数 PK_BODY_slice 签名, DIS argc=4 且第 2 参 = logical 字节, _r_f 约定 = 基参数 + frustrum |
| PK_BODY_slice_r_f | PK_ERROR_code_t PK_BODY_slice(PK_BODY_t body, PK_LOGICAL_t keep_both_sides, const PK_BODY_slice_o_t *options, PK_BODY_t *const results, PK_FRUSTUM_t *frustrum) | high | 基函数 PK_BODY_slice 签名, DIS argc=4 且第 2 参 = logical 字节, _r_f 约定 = 基参数 + frustrum |
| PK_FACE_ask_type | PK_ERROR_code_t PK_FACE_ask_type(PK_FACE_t face, PK_FACE_type_t *const type) | high | V35 ask 家族, DIS argc=2, PROBE rc=5022 guise |
| PK_FACE_ask_type_r_f | PK_ERROR_code_t PK_FACE_ask_type(PK_FACE_t face, PK_FACE_type_t *const type, PK_FRUSTUM_t *frustrum) | high | 基函数 PK_FACE_ask_type 签名, V35 ask 家族, DIS argc=2, PROBE rc=5022 guise, _r_f 约定 = 基参数 + frustrum |
| PK_FACE_identify_blends_2 | PK_ERROR_code_t PK_FACE_identify_blends_2(int n_faces, const PK_FACE_t faces[], const PK_FACE_identify_blends_o_t *options, PK_FACE_identify_blends_r_t *const results) | med | V35 identify_blends 同族, DIS argc=4 |
| PK_FACE_identify_blends_2_r_f | PK_ERROR_code_t PK_FACE_identify_blends_2(int n_faces, const PK_FACE_t faces[], const PK_FACE_identify_blends_o_t *options, PK_FACE_identify_blends_r_t *const results, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_FACE_identify_blends_2 签名, V35 identify_blends 同族, DIS argc=4, _r_f 约定 = 基参数 + frustrum |
| PK_FACE_pattern_2 | PK_ERROR_code_t PK_FACE_pattern_2(int n_pattern_faces, const PK_FACE_t pattern_faces[], int n_transforms, const PK_TRANSF_t transforms[], const PK_FACE_pattern_o_t *options, PK_FACE_pattern_r_t *const pattern_results) | med | V35 FACE_pattern 同族 + 2, DIS argc=6 |
| PK_FACE_pattern_2_r_f | PK_ERROR_code_t PK_FACE_pattern_2(int n_pattern_faces, const PK_FACE_t pattern_faces[], int n_transforms, const PK_TRANSF_t transforms[], const PK_FACE_pattern_o_t *options, PK_FACE_pattern_r_t *const pattern_results, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_FACE_pattern_2 签名, V35 FACE_pattern 同族 + 2, DIS argc=6, _r_f 约定 = 基参数 + frustrum |
| PK_FRAME_ask_body | PK_ERROR_code_t PK_FRAME_ask_body(PK_FRAME_t frame, PK_BODY_t *const body) | high | V35 ask 家族, DIS argc=2 |
| PK_FRAME_ask_geometry | PK_ERROR_code_t PK_FRAME_ask_geometry(PK_FRAME_t frame, PK_GEOM_t *const geometry) | high | V35 ask 家族, DIS argc=2 |
| PK_FRAME_ask_geometry_r_f | PK_ERROR_code_t PK_FRAME_ask_geometry(PK_FRAME_t frame, PK_GEOM_t *const geometry, PK_FRUSTUM_t *frustrum) | high | 基函数 PK_FRAME_ask_geometry 签名, V35 ask 家族, DIS argc=2, _r_f 约定 = 基参数 + frustrum |
| PK_FRAME_ask_owner | PK_ERROR_code_t PK_FRAME_ask_owner(PK_FRAME_t frame, PK_TOPOL_t *const owner) | med | V35 ask 家族, DIS argc=3 |
| PK_FRAME_ask_owner_r_f | PK_ERROR_code_t PK_FRAME_ask_owner(PK_FRAME_t frame, PK_TOPOL_t *const owner, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_FRAME_ask_owner 签名, V35 ask 家族, DIS argc=3, _r_f 约定 = 基参数 + frustrum |
| PK_FRAME_ask_sense | PK_ERROR_code_t PK_FRAME_ask_sense(PK_FRAME_t frame, PK_LOGICAL_t *const sense) | med | V35 ask 家族, DIS argc=3 |
| PK_FRAME_attach_geoms | PK_ERROR_code_t PK_FRAME_attach_geoms(PK_FRAME_t frame, int n_geoms, const PK_GEOM_t geoms[], PK_LOGICAL_t *const attached) | med | DIS argc=2/6, SCH FRAME |
| PK_FRAME_attach_geoms_r_f | PK_ERROR_code_t PK_FRAME_attach_geoms(PK_FRAME_t frame, int n_geoms, const PK_GEOM_t geoms[], PK_LOGICAL_t *const attached, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_FRAME_attach_geoms 签名, DIS argc=2/6, SCH FRAME, _r_f 约定 = 基参数 + frustrum |
| PK_FRAME_reverse | PK_ERROR_code_t PK_FRAME_reverse(PK_FRAME_t frame) | med | NOM, DIS |
| PK_FRAME_reverse_r_f | PK_ERROR_code_t PK_FRAME_reverse(PK_FRAME_t frame, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_FRAME_reverse 签名, NOM, DIS, _r_f 约定 = 基参数 + frustrum |
| PK_GEOM_enlarge | PK_ERROR_code_t PK_GEOM_enlarge(PK_GEOM_t geom, const PK_GEOM_enlarge_o_t *options) | med | DIS argc=1, NOM enlarge 家族 |
| PK_GEOM_enlarge_r_f | PK_ERROR_code_t PK_GEOM_enlarge(PK_GEOM_t geom, const PK_GEOM_enlarge_o_t *options, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_GEOM_enlarge 签名, DIS argc=1, NOM enlarge 家族, _r_f 约定 = 基参数 + frustrum |
| PK_LATTICE_ask_bound | PK_ERROR_code_t PK_LATTICE_ask_bound(PK_LATTICE_t lattice, PK_TOPOL_t *const bound) | med | V35 ask 家族, DIS argc=2 |
| PK_LATTICE_ask_bound_r_f | PK_ERROR_code_t PK_LATTICE_ask_bound(PK_LATTICE_t lattice, PK_TOPOL_t *const bound, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_LATTICE_ask_bound 签名, V35 ask 家族, DIS argc=2, _r_f 约定 = 基参数 + frustrum |
| PK_LATTICE_ask_cell | PK_ERROR_code_t PK_LATTICE_ask_cell(PK_LATTICE_t lattice, PK_TOPOL_t *const cell) | med | V35 ask 家族 |
| PK_LATTICE_ask_cell_r_f | PK_ERROR_code_t PK_LATTICE_ask_cell(PK_LATTICE_t lattice, PK_TOPOL_t *const cell, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_LATTICE_ask_cell 签名, V35 ask 家族, _r_f 约定 = 基参数 + frustrum |
| PK_LATTICE_ask_connectivity | PK_ERROR_code_t PK_LATTICE_ask_connectivity(PK_LATTICE_t lattice, int *const n_links, PK_LATTICE_link_t **const links) | med | V35 ask 家族 |
| PK_LATTICE_ask_connectivity_r_f | PK_ERROR_code_t PK_LATTICE_ask_connectivity(PK_LATTICE_t lattice, int *const n_links, PK_LATTICE_link_t **const links, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_LATTICE_ask_connectivity 签名, V35 ask 家族, _r_f 约定 = 基参数 + frustrum |
| PK_LATTICE_ask_core | PK_ERROR_code_t PK_LATTICE_ask_core(PK_LATTICE_t lattice, PK_GEOM_t *const core) | med | V35 ask 家族 |
| PK_LATTICE_ask_core_r_f | PK_ERROR_code_t PK_LATTICE_ask_core(PK_LATTICE_t lattice, PK_GEOM_t *const core, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_LATTICE_ask_core 签名, V35 ask 家族, _r_f 约定 = 基参数 + frustrum |
| PK_LATTICE_ask_form | PK_ERROR_code_t PK_LATTICE_ask_form(PK_LATTICE_t lattice, PK_LATTICE_form_t *const form) | med | DIS argc=1, SCH LATTICE |
| PK_LATTICE_ask_form_r_f | PK_ERROR_code_t PK_LATTICE_ask_form(PK_LATTICE_t lattice, PK_LATTICE_form_t *const form, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_LATTICE_ask_form 签名, DIS argc=1, SCH LATTICE, _r_f 约定 = 基参数 + frustrum |
| PK_LATTICE_ask_regions | PK_ERROR_code_t PK_LATTICE_ask_regions(PK_LATTICE_t lattice, int *const n_regions, PK_REGION_t **const regions) | med | V35 ask 家族, DIS argc=2 |
| PK_LATTICE_ask_regions_r_f | PK_ERROR_code_t PK_LATTICE_ask_regions(PK_LATTICE_t lattice, int *const n_regions, PK_REGION_t **const regions, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_LATTICE_ask_regions 签名, V35 ask 家族, DIS argc=2, _r_f 约定 = 基参数 + frustrum |
| PK_LATTICE_ask_type | PK_ERROR_code_t PK_LATTICE_ask_type(PK_LATTICE_t lattice, PK_LATTICE_type_t *const type) | high | DIS 薄 getter [rcx]=tag, SCH LATTICE |
| PK_LATTICE_ask_type_r_f | PK_ERROR_code_t PK_LATTICE_ask_type(PK_LATTICE_t lattice, PK_LATTICE_type_t *const type, PK_FRUSTUM_t *frustrum) | high | 基函数 PK_LATTICE_ask_type 签名, DIS 薄 getter [rcx]=tag, SCH LATTICE, _r_f 约定 = 基参数 + frustrum |
| PK_LATTICE_combine | PK_ERROR_code_t PK_LATTICE_combine(int n_lattices, const PK_LATTICE_t lattices[], const PK_LATTICE_combine_o_t *options, PK_LATTICE_t *const combined) | med | DIS argc=1/4, SCH LATTICE |
| PK_LATTICE_combine_r_f | PK_ERROR_code_t PK_LATTICE_combine(int n_lattices, const PK_LATTICE_t lattices[], const PK_LATTICE_combine_o_t *options, PK_LATTICE_t *const combined, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_LATTICE_combine 签名, DIS argc=1/4, SCH LATTICE, _r_f 约定 = 基参数 + frustrum |
| PK_LATTICE_create_by_core | PK_ERROR_code_t PK_LATTICE_create_by_core(const PK_LATTICE_create_by_core_o_t *options, PK_LATTICE_t *const lattice) | med | DIS argc=10(栈参多), SCH LATTICE |
| PK_LATTICE_create_by_core_r_f | PK_ERROR_code_t PK_LATTICE_create_by_core(const PK_LATTICE_create_by_core_o_t *options, PK_LATTICE_t *const lattice, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_LATTICE_create_by_core 签名, DIS argc=10(栈参多), SCH LATTICE, _r_f 约定 = 基参数 + frustrum |
| PK_LATTICE_disjoin | PK_ERROR_code_t PK_LATTICE_disjoin(PK_LATTICE_t lattice, const PK_LATTICE_disjoin_o_t *options, PK_LATTICE_t *const results) | med | DIS argc=1, SCH LATTICE |
| PK_LATTICE_disjoin_r_f | PK_ERROR_code_t PK_LATTICE_disjoin(PK_LATTICE_t lattice, const PK_LATTICE_disjoin_o_t *options, PK_LATTICE_t *const results, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_LATTICE_disjoin 签名, DIS argc=1, SCH LATTICE, _r_f 约定 = 基参数 + frustrum |
| PK_LATTICE_find_nabox | PK_ERROR_code_t PK_LATTICE_find_nabox(PK_LATTICE_t lattice, int *const n_naboxes, PK_LATTICE_nabox_t **const naboxes) | med | V35 ask 家族, DIS argc=2 |
| PK_LATTICE_find_nabox_r_f | PK_ERROR_code_t PK_LATTICE_find_nabox(PK_LATTICE_t lattice, int *const n_naboxes, PK_LATTICE_nabox_t **const naboxes, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_LATTICE_find_nabox 签名, V35 ask 家族, DIS argc=2, _r_f 约定 = 基参数 + frustrum |
| PK_LATTICE_make_patterned | PK_ERROR_code_t PK_LATTICE_make_patterned(int n_lattices, const PK_LATTICE_t lattices[], const PK_LATTICE_make_patterned_o_t *options, PK_LATTICE_make_patterned_r_t *const results) | med | DIS argc=1, SCH PATTERN_* |
| PK_LATTICE_make_patterned_r_f | PK_ERROR_code_t PK_LATTICE_make_patterned(int n_lattices, const PK_LATTICE_t lattices[], const PK_LATTICE_make_patterned_o_t *options, PK_LATTICE_make_patterned_r_t *const results, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_LATTICE_make_patterned 签名, DIS argc=1, SCH PATTERN_*, _r_f 约定 = 基参数 + frustrum |
| PK_LATTICE_offset | PK_ERROR_code_t PK_LATTICE_offset(PK_LATTICE_t lattice, const PK_LATTICE_offset_o_t *options, PK_LATTICE_t *const offset) | med | DIS argc=6, SCH LATTICE |
| PK_LATTICE_offset_r_f | PK_ERROR_code_t PK_LATTICE_offset(PK_LATTICE_t lattice, const PK_LATTICE_offset_o_t *options, PK_LATTICE_t *const offset, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_LATTICE_offset 签名, DIS argc=6, SCH LATTICE, _r_f 约定 = 基参数 + frustrum |
| PK_LBALL_ask_blend | PK_ERROR_code_t PK_LBALL_ask_blend(PK_LBALL_t lball, PK_GEOM_t *const blend) | med | V35 ask 家族 |
| PK_LBALL_ask_blend_r_f | PK_ERROR_code_t PK_LBALL_ask_blend(PK_LBALL_t lball, PK_GEOM_t *const blend, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_LBALL_ask_blend 签名, V35 ask 家族, _r_f 约定 = 基参数 + frustrum |
| PK_MARK_create_2 | PK_ERROR_code_t PK_MARK_create_2(int n_topols, const PK_TOPOL_t topols[], const PK_MARK_create_o_t *options, PK_MARK_t *const marks) | med | V35 MARK_create 同族 + 2 |
| PK_MARK_create_r_f | PK_ERROR_code_t PK_MARK_create_2(int n_topols, const PK_TOPOL_t topols[], const PK_MARK_create_o_t *options, PK_MARK_t *const marks, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_MARK_create_2 签名, V35 MARK_create 同族 + 2, _r_f 约定 = 基参数 + frustrum |
| PK_MARK_delete_2 | PK_ERROR_code_t PK_MARK_delete_2(int n_marks, const PK_MARK_t marks[], const PK_MARK_delete_o_t *options) | med | V35 MARK_delete 同族 + 2 |
| PK_MARK_delete_r_f | PK_ERROR_code_t PK_MARK_delete_2(int n_marks, const PK_MARK_t marks[], const PK_MARK_delete_o_t *options, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_MARK_delete_2 签名, V35 MARK_delete 同族 + 2, _r_f 约定 = 基参数 + frustrum |
| PK_PARTITION_ask | PK_ERROR_code_t PK_PARTITION_ask(PK_PARTITION_t partition, PK_PARTITION_ask_o_t *const options) | med | V35 ask 家族 |
| PK_PARTITION_ask_pmarks_2 | PK_ERROR_code_t PK_PARTITION_ask_pmarks_2(PK_PARTITION_t partition, int *const n_pmarks, PK_PMARK_t **const pmarks) | med | V35 ask 家族 |
| PK_PARTITION_ask_pmarks_2_r_f | PK_ERROR_code_t PK_PARTITION_ask_pmarks_2(PK_PARTITION_t partition, int *const n_pmarks, PK_PMARK_t **const pmarks, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_PARTITION_ask_pmarks_2 签名, V35 ask 家族, _r_f 约定 = 基参数 + frustrum |
| PK_PARTITION_ask_r_f | PK_ERROR_code_t PK_PARTITION_ask(PK_PARTITION_t partition, PK_PARTITION_ask_o_t *const options, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_PARTITION_ask 签名, V35 ask 家族, _r_f 约定 = 基参数 + frustrum |
| PK_PARTITION_clear_guard | PK_ERROR_code_t PK_PARTITION_clear_guard(PK_PARTITION_t partition) | med | NOM |
| PK_PARTITION_create | PK_ERROR_code_t PK_PARTITION_create(PK_BODY_t body, PK_PARTITION_t *const partition) | med | NOM, SCH PARTITION |
| PK_PARTITION_create_r_f | PK_ERROR_code_t PK_PARTITION_create(PK_BODY_t body, PK_PARTITION_t *const partition, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_PARTITION_create 签名, NOM, SCH PARTITION, _r_f 约定 = 基参数 + frustrum |
| PK_PARTITION_goto_guard | PK_ERROR_code_t PK_PARTITION_goto_guard(PK_PARTITION_t partition, PK_PARTITION_t *const guard) | med | NOM |
| PK_PARTITION_goto_guard_r_f | PK_ERROR_code_t PK_PARTITION_goto_guard(PK_PARTITION_t partition, PK_PARTITION_t *const guard, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_PARTITION_goto_guard 签名, NOM, _r_f 约定 = 基参数 + frustrum |
| PK_PARTITION_has_guard | PK_ERROR_code_t PK_PARTITION_has_guard(PK_PARTITION_t partition, PK_LOGICAL_t *const has_guard) | med | V35 is/has 家族 |
| PK_PARTITION_has_lattices | PK_ERROR_code_t PK_PARTITION_has_lattices(PK_PARTITION_t partition, PK_LOGICAL_t *const has_lattices) | med | V35 is/has 家族 |
| PK_PARTITION_has_lattices_r_f | PK_ERROR_code_t PK_PARTITION_has_lattices(PK_PARTITION_t partition, PK_LOGICAL_t *const has_lattices, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_PARTITION_has_lattices 签名, V35 is/has 家族, _r_f 约定 = 基参数 + frustrum |
| PK_PARTITION_set_guard | PK_ERROR_code_t PK_PARTITION_set_guard(PK_PARTITION_t partition, PK_PARTITION_t guard) | med | NOM |
| PK_PARTITION_set_guard_r_f | PK_ERROR_code_t PK_PARTITION_set_guard(PK_PARTITION_t partition, PK_PARTITION_t guard, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_PARTITION_set_guard 签名, NOM, _r_f 约定 = 基参数 + frustrum |
| PK_REGION_ask_lattices | PK_ERROR_code_t PK_REGION_ask_lattices(PK_REGION_t region, int *const n_lattices, PK_LATTICE_t **const lattices) | high | V35 ask 家族, DIS argc=2/3, PROBE rc=5022 guise |
| PK_REGION_ask_lattices_r_f | PK_ERROR_code_t PK_REGION_ask_lattices(PK_REGION_t region, int *const n_lattices, PK_LATTICE_t **const lattices, PK_FRUSTUM_t *frustrum) | high | 基函数 PK_REGION_ask_lattices 签名, V35 ask 家族, DIS argc=2/3, PROBE rc=5022 guise, _r_f 约定 = 基参数 + frustrum |
| PK_REGION_ask_type | PK_ERROR_code_t PK_REGION_ask_type(PK_REGION_t region, PK_REGION_type_t *const type) | high | V35 ask 家族, DIS argc=2, PROBE rc=5022 guise |
| PK_REGION_ask_type_r_f | PK_ERROR_code_t PK_REGION_ask_type(PK_REGION_t region, PK_REGION_type_t *const type, PK_FRUSTUM_t *frustrum) | high | 基函数 PK_REGION_ask_type 签名, V35 ask 家族, DIS argc=2, PROBE rc=5022 guise, _r_f 约定 = 基参数 + frustrum |
| PK_REGION_embed_body | PK_ERROR_code_t PK_REGION_embed_body(PK_REGION_t region, PK_BODY_t body) | med | NOM, SCH REGION |
| PK_REGION_embed_body_r_f | PK_ERROR_code_t PK_REGION_embed_body(PK_REGION_t region, PK_BODY_t body, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_REGION_embed_body 签名, NOM, SCH REGION, _r_f 约定 = 基参数 + frustrum |
| PK_REGION_embed_lattices | PK_ERROR_code_t PK_REGION_embed_lattices(PK_REGION_t region, int n_lattices, const PK_LATTICE_t lattices[]) | med | NOM, SCH REGION |
| PK_REGION_embed_lattices_r_f | PK_ERROR_code_t PK_REGION_embed_lattices(PK_REGION_t region, int n_lattices, const PK_LATTICE_t lattices[], PK_FRUSTUM_t *frustrum) | med | 基函数 PK_REGION_embed_lattices 签名, NOM, SCH REGION, _r_f 约定 = 基参数 + frustrum |
| PK_REGION_remove_lattice | PK_ERROR_code_t PK_REGION_remove_lattice(PK_REGION_t region, PK_LATTICE_t lattice) | med | NOM, SCH REGION |
| PK_REGION_remove_lattice_r_f | PK_ERROR_code_t PK_REGION_remove_lattice(PK_REGION_t region, PK_LATTICE_t lattice, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_REGION_remove_lattice 签名, NOM, SCH REGION, _r_f 约定 = 基参数 + frustrum |
| PK_SESSION_ask_cellular_guise | PK_ERROR_code_t PK_SESSION_ask_cellular_guise(PK_LOGICAL_t *const cellular_guise) | high | PROBE rc=0 (guise=27110) |
| PK_SESSION_set_cellular_guise | PK_ERROR_code_t PK_SESSION_set_cellular_guise(PK_LOGICAL_t cellular_guise) | med | 对偶 ask_cellular_guise（PROBE 已证 ask） |
| PK_TOPOL_find_connected | PK_ERROR_code_t PK_TOPOL_find_connected(PK_TOPOL_t topol, int *const n_connected, PK_TOPOL_t **const connected) | med | V35 find 家族 |
| PK_TOPOL_find_connected_r_f | PK_ERROR_code_t PK_TOPOL_find_connected(PK_TOPOL_t topol, int *const n_connected, PK_TOPOL_t **const connected, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_TOPOL_find_connected 签名, V35 find 家族, _r_f 约定 = 基参数 + frustrum |
| PK_TOPOL_find_frames | PK_ERROR_code_t PK_TOPOL_find_frames(PK_TOPOL_t topol, int *const n_frames, PK_FRAME_t **const frames) | med | V35 find 家族 |
| PK_TOPOL_find_frames_r_f | PK_ERROR_code_t PK_TOPOL_find_frames(PK_TOPOL_t topol, int *const n_frames, PK_FRAME_t **const frames, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_TOPOL_find_frames 签名, V35 find 家族, _r_f 约定 = 基参数 + frustrum |
| PK_TOPOL_imprint_frames | PK_ERROR_code_t PK_TOPOL_imprint_frames(PK_TOPOL_t topol, int n_frames, const PK_FRAME_t frames[]) | med | NOM, SCH FRAME |
| PK_TOPOL_imprint_frames_r_f | PK_ERROR_code_t PK_TOPOL_imprint_frames(PK_TOPOL_t topol, int n_frames, const PK_FRAME_t frames[], PK_FRUSTUM_t *frustrum) | med | 基函数 PK_TOPOL_imprint_frames 签名, NOM, SCH FRAME, _r_f 约定 = 基参数 + frustrum |
| PK_TOPOL_is_connected | PK_ERROR_code_t PK_TOPOL_is_connected(PK_TOPOL_t topol_1, PK_TOPOL_t topol_2, PK_LOGICAL_t *const is_connected) | med | V35 is/has 家族 |
| PK_TOPOL_is_connected_r_f | PK_ERROR_code_t PK_TOPOL_is_connected(PK_TOPOL_t topol_1, PK_TOPOL_t topol_2, PK_LOGICAL_t *const is_connected, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_TOPOL_is_connected 签名, V35 is/has 家族, _r_f 约定 = 基参数 + frustrum |
| PK_TOPOL_render_volume | PK_ERROR_code_t PK_TOPOL_render_volume(PK_TOPOL_t topol, const PK_TOPOL_render_volume_o_t *options, PK_TOPOL_render_volume_r_t *const results) | med | NOM, DIS |
| PK_TOPOL_render_volume_r_f | PK_ERROR_code_t PK_TOPOL_render_volume(PK_TOPOL_t topol, const PK_TOPOL_render_volume_o_t *options, PK_TOPOL_render_volume_r_t *const results, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_TOPOL_render_volume 签名, NOM, DIS, _r_f 约定 = 基参数 + frustrum |
| PK_TRANSF_enlarge | PK_ERROR_code_t PK_TRANSF_enlarge(PK_TRANSF_t transf, const PK_TRANSF_enlarge_o_t *options) | med | NOM enlarge 家族 |
| PK_TRANSF_enlarge_r_f | PK_ERROR_code_t PK_TRANSF_enlarge(PK_TRANSF_t transf, const PK_TRANSF_enlarge_o_t *options, PK_FRUSTUM_t *frustrum) | med | 基函数 PK_TRANSF_enlarge 签名, NOM enlarge 家族, _r_f 约定 = 基参数 + frustrum |
