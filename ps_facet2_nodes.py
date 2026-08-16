"""Standalone reverse-engineered scSTREAM Pre x_t -> facet nodes generator.

This script reproduces, in pure ctypes, the node-generation path that
scSTREAM Pre uses to turn Parasolid ``.x_t`` B-rep bodies into display
mesh nodes (vertices + triangles).  It was written from disassembly of
the Cradle CFD 2025.2 binaries under ``Programs_x64``:

Call chain (all RVAs are relative to the DLL image base 0x180000000):

  STpreBase_Bx64.dll
    ?MakeFacet@PreBody@@QEAAHHPEAVFacetParam@@@Z        RVA 0x293A20
    ?MakeFacetParam@PreBody@@QEAAPEAVFacetParam@@QEAN@Z RVA 0x293C20
      |  (FacetParam carries the chord/surface tolerances, see
      |   ?Get@FacetParam@@QEAAXPEAN@Z RVA 0x36160)
      v
  ParasolidGW_Bx64.dll  (Cradle's Parasolid wrapper)
    ?PKBody_GetTriangles@LocalParasolid@@...            RVA 0xA49A0 etc.
    ?PKFaces_RenderV3@LocalParasolid@@...               RVA 0x1415C0 / 0x141850
      |  (fills PK_TOPOL_facet_2_o_t, then calls virtual slot vtable+0x1C50)
      v
  pskernel.dll  (the actual Parasolid kernel)
    PK_TOPOL_facet_2                                    RVA 0x44DFA0
    PK_TOPOL_facet_2_r_f                                RVA 0x44FCE0

The kernel is commercial closed-source, so the *facet geometry algorithm*
itself (surface sampling, chord/angle subdivision, fin generation) cannot
be copied.  What the disassembly does give us - and what this script
implements - is the exact public API contract used by STpre:

* ``PK_TOPOL_facet_2`` accepts ``PK_TOPOL_facet_2_o_t`` whose version is
  in range 5..26 (the option converter at pskernel RVA 0x443550 switches
  on ``version-5`` with a 22-entry jump table).
* The version-5 option layout is a 312-byte mesh-control block followed by
  **18 consecutive byte flags** at offsets 0x138..0x149.  Each flag
  requests one facet table (converter writes caller bytes 0x138..0x149
  into the internal choice flags at 0x1C8..0x1DF).
* Table tokens (fctab) observed on this kernel (the V35 documentation
  order and the kernel's own V5 enum differ in the middle block):

    0x57B2 facet_fin      0x57B7 data_point_idx 0x57BD data_curv_idx
    0x57B3 strip_boundary 0x57B8 data_normal_idx 0x57BE param_uv
    0x57B4 strip_zigzag   0x57B9 data_param_idx  0x57BF deriv_dp
    0x57B5 fin_fin        0x57BA data_deriv_idx  0x57C0 deriv_d2p
    0x57B6 fin_data       0x57BB point_vec       0x57C1 curv_dirs
                         0x57BC normal_vec       0x57C2 fin_edge
                                                 0x57C3 strip_face

  i.e. the kernel places ``point_vec``/``normal_vec`` *before*
  ``data_curv_idx``, opposite to the V35 header order.  This was confirmed
  three ways: single-choice probes (offset 0x141 -> token 0x57BB etc.),
  data semantics (0x57BB holds the 8 box corners, identical to the GO
  path), and STpre's own table decoder in ParasolidGW_Bx64.dll, which
  reads 24-byte coordinates from the table stored in its ``data_curv_idx``
  slot (token 0x57BB).

  (ParasolidGW's ``?PKTopol_facet_2_r_f@...`` at RVA 0x18B290 frees a
  16-byte table entry array; it switches on ``fctab-0x57B2`` with 18
  cases, which is exactly the 18 flags above.  pskernel's own
  ``PK_TOPOL_facet_2_r_f`` switches on ``fctab-0x57B2`` with 25 cases,
  i.e. this kernel also knows the newer fin_edge/point_topol/fin_topol/
  error_object/incr_faces tables.)
* Every table pointer in ``PK_TOPOL_facet_2_r_t.tables[]`` points to a
  16-byte wrapper whose first qword is the actual data array and whose
  second dword is the element count (``PK_TOPOL_fctab_*_t`` layout:
  ``{ pointer-to-data; int length; }``).
* Data encodings observed on this kernel (V35 header ``pk_topol_fctab_*_t``):
  - facet_fin:       lookup table of 8-byte records ``{int facet; int fin}``,
    ``length`` records, 3 consecutive records per triangle facet
  - fin_data:        indexed table ``int data[fin]`` (length = fins)
  - data_point_idx:  indexed table ``int point[data]``
    (length = data indices; ``data[fin]`` indexes into it)
  - point_vec:       indexed table of ``length`` PK_VECTOR_t entries
    (24 bytes each: x, y, z doubles); entry i is the coordinate of point i
    (token 0x57BB on this kernel)
  - normal_vec:      same layout, unit face normals (token 0x57BC)
  - fin_edge:        8-byte records ``{int fin; PK_EDGE_t edge}``.  The
    kernel's token 0x57C2 is *not* the V35-documented facet_face table; it
    maps the two boundary fins of every triangle facet to the model edge
    they lie on (verified on box against PK_BODY_ask_edges: 12 distinct edge
    tags, each appearing twice; the 12 missing fins are the face-interior
    diagonals, i.e. fin indices 3*facet).
* To call the kernel from a foreign process the argument checker must be
  disabled (``PK_SESSION_set_check_arguments(0)``), otherwise a struct
  version mismatch raises ``PK_ERROR_o_t_version_incorrect`` (5022)
  before any faceting happens.  STpre itself always passes a matching
  version; the checker-off call is the reverse-engineering workaround.

Facet geometry is generated by ``PK_TOPOL_facet_2`` exactly as STpre does
(the wrapper sets ``max_facet_sides=3`` plus explicit surface plane
tolerance/angle; ``PKFaces_RenderV3`` at RVA 0x141850 additionally scales
the chord tolerance by body size).  The returned tables are then walked
facet -> fin -> data -> point -> coordinate to produce node/triangle
arrays.

If ``PK_TOPOL_facet_2`` is unavailable or returns no tables, the script
falls back to ``PK_TOPOL_render_facet`` (GO callback path, same kernel),
which is the equivalent display-faceting route also used by
``ps_tessellate.py``.

Usage:
    python ps_facet2_nodes.py tests/box/_box_all.x_t
    python ps_facet2_nodes.py --obj out.obj tests/tr03/_tr03_all.x_t
"""

from __future__ import annotations

import argparse
import ctypes as C
import os
import struct
import tempfile
from ctypes import (
    CFUNCTYPE, POINTER, Structure, byref, c_byte, c_char, c_char_p,
    c_double, c_int, c_void_p, cast, memmove, memset, sizeof, string_at,
)
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Reverse-engineered constants
# ---------------------------------------------------------------------------

# PK_TOPOL_fctab_*_c tokens (pskernel facet tables), base 0x57B2.
FCTAB_FACET_FIN = 0x57B2
FCTAB_STRIP_BOUNDARY = 0x57B3
FCTAB_STRIP_ZIGZAG = 0x57B4
FCTAB_FIN_FIN = 0x57B5
FCTAB_FIN_DATA = 0x57B6
FCTAB_DATA_POINT_IDX = 0x57B7
FCTAB_DATA_NORMAL_IDX = 0x57B8
FCTAB_DATA_PARAM_IDX = 0x57B9
FCTAB_DATA_DERIV_IDX = 0x57BA
FCTAB_DATA_CURV_IDX = 0x57BD
FCTAB_POINT_VEC = 0x57BB
FCTAB_NORMAL_VEC = 0x57BC
FCTAB_PARAM_UV = 0x57BE
FCTAB_DERIV_DP = 0x57BF
FCTAB_DERIV_D2P = 0x57C0
FCTAB_CURV_DIRS = 0x57C1
FCTAB_FACET_FACE = 0x57C2
FCTAB_STRIP_FACE = 0x57C3

# Choice byte offsets inside PK_TOPOL_facet_2_o_t version 5 (control is
# 0x138 bytes; the 18 flags follow at 0x138..0x149).  NOTE: the kernel's V5
# layout puts point_vec/normal_vec *before* data_curv_idx (verified by
# single-choice probes and by the returned data), unlike the V35 docs.
CHOICE_OFFSET = {
    "facet_fin": 0x138, "strip_boundary": 0x139, "strip_zigzag": 0x13A,
    "fin_fin": 0x13B, "fin_data": 0x13C, "data_point_idx": 0x13D,
    "data_normal_idx": 0x13E, "data_param_idx": 0x13F,
    "data_deriv_idx": 0x140, "point_vec": 0x141, "normal_vec": 0x142,
    "data_curv_idx": 0x143, "param_uv": 0x144, "deriv_dp": 0x145,
    "deriv_d2p": 0x146, "curv_dirs": 0x147, "fin_edge": 0x148,
    "strip_face": 0x149,
}

_DEFAULT_CRADLE = Path(r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64")
DEFAULT_FACET_TOL = 1e-4        # surface-to-facet distance bound
DEFAULT_FACET_ANGLE_DEG = 12.0  # max normal swing per facet (degrees)

# Adaptive refinement defaults (see tessellate_xt / facet_body_adaptive).
DEFAULT_REFINE_ANGLE_DEG = 6.0  # local surface_plane_ang for selected faces
DEFAULT_REFINE_TOL = 1e-5       # local surface_plane_tol for selected faces
DEFAULT_SMOOTH_ANGLE_DEG = 8.0  # refine faces whose intra-face dihedral > this
DEFAULT_MIN_REL_AREA = 1e-4     # face area must be >= this * body bbox area
DEFAULT_MIN_FACE_FACETS = 8     # skip trivial faces with fewer facets

# GO segment types used by the render_facet fallback.
_SGTPFT = 2016  # facet segment


@dataclass
class TessPart:
    """Tessellated CAD body: node list + triangle list."""

    name: str
    points: np.ndarray          # (N, 3) float64
    triangles: np.ndarray       # (M, 3) int32 into points
    tag: int = 0
    vertices: Optional[np.ndarray] = None  # real B-rep vertices (M, 3)


# ---------------------------------------------------------------------------
# PK_TOPOL_facet_2_o_t, version 5 (layout recovered from the option
# converter disassembly at pskernel RVA 0x443550, case "version-5").
# ---------------------------------------------------------------------------


class _MeshControlV5(Structure):
    """PK_TOPOL_facet_mesh_2_o_t, version 5: 312 bytes."""

    _fields_ = [
        ("o_t_version", c_int),
        ("shape", c_int), ("match", c_int), ("density", c_int),
        ("n_view_directions", c_int), ("_pad0", c_int),
        ("view_directions", c_void_p),
        ("cull", c_int), ("n_cull_transfs", c_int), ("cull_transfs", c_void_p),
        ("n_loops", c_int), ("_pad1", c_int), ("loops", c_void_p),
        ("max_facet_sides", c_int),
        ("is_min_facet_width", c_int), ("min_facet_width", c_double),
        ("is_max_facet_width", c_int), ("_pad2", c_int),
        ("max_facet_width", c_double),
        ("is_curve_chord_tol", c_int), ("_pad3", c_int),
        ("curve_chord_tol", c_double),
        ("is_curve_chord_max", c_int), ("_pad4", c_int),
        ("curve_chord_max", c_double),
        ("is_curve_chord_ang", c_int), ("_pad5", c_int),
        ("curve_chord_ang", c_double),
        ("is_surface_plane_tol", c_int), ("_pad6", c_int),
        ("surface_plane_tol", c_double),
        ("is_surface_plane_ang", c_int), ("_pad7", c_int),
        ("surface_plane_ang", c_double),
        ("is_facet_plane_tol", c_int), ("_pad8", c_int),
        ("facet_plane_tol", c_double),
        ("is_facet_plane_ang", c_int), ("_pad9", c_int),
        ("facet_plane_ang", c_double),
        ("is_local_density_tol", c_int), ("_pad10", c_int),
        ("local_density_tol", c_double),
        ("is_local_density_ang", c_int), ("_pad11", c_int),
        ("local_density_ang", c_double),
        ("n_local_tols", c_int), ("_pad12", c_int), ("local_tols", c_void_p),
        ("n_topols_with_local_tols", c_int), ("_pad13", c_int),
        ("topols_with_local_tols", c_void_p),
        ("local_tols_for_topols", c_void_p),
        ("ignore", c_int), ("_pad14", c_int), ("ignore_value", c_double),
        ("ignore_scope", c_int), ("wire_edges", c_int),
        ("incremental_facetting", c_int), ("incremental_method", c_int),
    ]


class _Facet2OptionsV5(Structure):
    """PK_TOPOL_facet_2_o_t, version 5: control + 18 byte choice flags."""

    _fields_ = [("control", _MeshControlV5)] + [
        (name, c_byte) for name in CHOICE_OFFSET
    ]


class _Facet2Result(Structure):
    """PK_TOPOL_facet_2_r_t."""

    _fields_ = [
        ("number_of_facets", c_int),
        ("number_of_strips", c_int),
        ("number_of_fins", c_int),
        ("number_of_tables", c_int),
        ("tables", c_void_p),
    ]


class _FacetTable(Structure):
    """PK_TOPOL_facet_table_t: token + union pointer (16 bytes)."""

    _fields_ = [("fctab", c_int), ("_pad", c_int), ("ptr", c_void_p)]


class _FacetLocalTolerances(Structure):
    """PK_facet_local_tolerances_t: 5 doubles, zero keeps the global value."""

    _fields_ = [
        ("curve_chord_tol", c_double),
        ("curve_chord_max", c_double),
        ("curve_chord_ang", c_double),
        ("surface_plane_tol", c_double),
        ("surface_plane_ang", c_double),
    ]


# ---------------------------------------------------------------------------
# Kernel session (FRU + GO callbacks), same contract as ps_tessellate.py
# ---------------------------------------------------------------------------

_session: Optional["_PsSession"] = None


def find_cradle_programs() -> Optional[Path]:
    env = os.environ.get("CRADLE_PROGRAMS") or os.environ.get("P_SCHEMA")
    candidates: list[Path] = []
    if env:
        p = Path(env)
        candidates.append(p if p.name.lower() != "schemas" else p.parent)
    candidates.append(_DEFAULT_CRADLE)
    cradle_root = Path(r"C:\Program Files\Cradle")
    if cradle_root.is_dir():
        for child in sorted(cradle_root.glob("CradleCFD*/Programs_x64"),
                            reverse=True):
            candidates.append(child)
    seen: set[Path] = set()
    for c in candidates:
        c = c.resolve() if c.exists() else c
        if c in seen:
            continue
        seen.add(c)
        if (c / "pskernel.dll").is_file() and (c / "Schemas").is_dir():
            return c
    return None


def available() -> bool:
    """True when a Cradle ``pskernel.dll`` install can be located."""
    return find_cradle_programs() is not None


class _FRU(Structure):
    _fields_ = [(n, c_void_p) for n in (
        "fstart fabort fstop fmallo fmfree gosgmt goopsg goclsg gopixl "
        "gooppx goclpx ffoprd ffopwr ffclos ffread ffwrit ffoprb ffseek "
        "fftell fgcrcu fgcrsu fgevcu fgevsu fgprcu fgprsu ucoprd ucopwr"
    ).split()]


class _START(Structure):
    _fields_ = [("o_t_version", c_int), ("journal_file", c_char_p),
                ("user_field", c_int), ("reserved", c_int)]


class _TRANSMIT(Structure):
    """PK_PART_transmit_o_t（对齐 cabdecoding，6 字段）。"""

    _fields_ = [
        ("o_t_version", c_int),
        ("transmit_format", c_int),   # 0 = text
        ("transmit_user_fields", c_int),
        ("transmit_nw_version", c_int),
        ("transmit_xmt_file", c_int),
        ("transmit_attr", c_int),
    ]


class _RECV(Structure):
    _fields_ = [
        ("o_t_version", c_int), ("transmit_format", c_int),
        ("receive_user_fields", c_int), ("attdef_mismatch", c_int),
        ("part_index", c_int), ("n_part_indices", c_int),
        ("part_indices", c_void_p), ("n_identifiers", c_int),
        ("identifiers", c_void_p), ("receive_indexed_context", c_void_p),
        ("key_is_partition", c_int), ("receive_compound", c_int),
        ("receive_using_seek", c_int), ("receive_mixed", c_int),
    ]

# --- Parasolid 编辑 token（V35 数值码，对齐 cabdecoding）----------------
PK_boolean_intersect_c = 15901
PK_boolean_subtract_c = 15902
PK_boolean_unite_c = 15903
PK_boolean_fence_none_c = 18212
PK_boolean_check_fa_yes_c = 21801
PK_FACE_heal_cap_c = 18081
PK_FACE_heal_shrink_c = 18084
PK_local_ops_update_default_c = 24330
PK_repair_fa_fa_no_c = 24360
PK_delete_track_no_c = 26340

_BOOLEAN_OP_FUNC = {
    "unite": PK_boolean_unite_c,
    "subtract": PK_boolean_subtract_c,
    "intersect": PK_boolean_intersect_c,
}


class _BooleanOpts(Structure):
    """PK_BODY_boolean_o_t（cabdecoding 已实测 o_t_version=2）。"""

    _fields_ = [
        ("o_t_version", c_int),
        ("function", c_int),
        ("configuration", c_void_p),
        ("matched_region", c_void_p),
        ("merge_imprinted", c_int),
        ("prune_in_solid", c_int),
        ("prune_in_void", c_int),
        ("fence", c_int),
        ("allow_disjoint", c_int),
        ("selective_merge", c_int),
        ("check_fa", c_int),
        ("default_tol", c_double),
        ("max_tol", c_double),
        ("tracking", c_int),
        ("merge_attributes", c_int),
        ("keep_target_edges", c_int),
    ]


class _TrackR(Structure):
    _fields_ = [
        ("n_track_records", c_int),
        ("track_records", c_void_p),
        ("internal_origs", c_void_p),
        ("internal_classes", c_void_p),
        ("internal_prods", c_void_p),
    ]


class _BooleanR(Structure):
    _fields_ = [
        ("result", c_int),
        ("n_bodies", c_int),
        ("bodies", POINTER(c_int)),
        ("n_reports", c_int),
        ("reports", c_void_p),
    ]


class _AXIS2(Structure):
    """PK_AXIS2_sf_t：坐标系（location + axis + ref_direction）。"""

    _fields_ = [
        ("location", c_double * 3),
        ("axis", c_double * 3),
        ("ref_direction", c_double * 3),
    ]


class _BodyTransformOpts(Structure):
    """PK_BODY_transform_o_t（V37，4 int；o_t_version=1 实测可用）。"""

    _fields_ = [
        ("o_t_version", c_int),
        ("merge_face", c_int),
        ("check_fa_fa", c_int),
        ("update", c_int),
    ]


class _FaceDeleteOpts(Structure):
    """PK_FACE_delete_o_t（cabdecoding 已实测 o_t_version=1）。"""

    _fields_ = [
        ("o_t_version", c_int),
        ("update", c_int),
        ("heal_action", c_int),
        ("heal_loops", c_int),
        ("local_check", c_int),
        ("allow_disjoint", c_int),
        ("repair_fa_fa", c_int),
        ("track", c_int),
    ]


class _PsSession:
    """One pskernel session with text x_t receive + facet_2 + GO fallback."""

    def __init__(self, prog: Path):
        self.prog = prog
        self.schema = prog / "Schemas"
        os.add_dll_directory(str(prog))
        os.environ["PATH"] = str(prog) + ";" + os.environ.get("PATH", "")
        os.environ["P_SCHEMA"] = str(self.schema)
        self.pk = C.WinDLL(str(prog / "pskernel.dll"))
        self._files: dict = {}
        self._write_files: dict = {}
        self._write_paths: dict = {}
        self._transmit_output: dict = {}
        self._next_id = 1
        self._mallo_bufs: list = []
        self._segs: list = []
        self._build_frustrum()
        self._start()

    # -- frustrum ----------------------------------------------------------
    def _build_frustrum(self) -> None:
        pk = self.pk
        files = self._files
        write_files = self._write_files
        write_paths = self._write_paths
        transmit_output = self._transmit_output
        schema = self.schema
        mallo = self._mallo_bufs
        segs = self._segs

        @CFUNCTYPE(None, POINTER(c_int))
        def FSTART(ifail):
            ifail[0] = 0

        @CFUNCTYPE(None, POINTER(c_int))
        def FSTOP(ifail):
            ifail[0] = 0

        @CFUNCTYPE(None, POINTER(c_int), POINTER(c_char_p), POINTER(c_int))
        def FMALLO(nbytes, memory, ifail):
            n = nbytes[0]
            buf = (c_char * n)()
            mallo.append(buf)
            memory[0] = cast(buf, c_char_p)
            ifail[0] = 0

        @CFUNCTYPE(None, POINTER(c_int), POINTER(c_char_p), POINTER(c_int))
        def FMFREE(n, m, i):
            i[0] = 0

        @CFUNCTYPE(
            None, POINTER(c_int), POINTER(c_int), c_void_p, POINTER(c_int),
            POINTER(c_int), POINTER(c_int), POINTER(c_int),
        )
        def FFOPRD(guise, format_, name, namlen, skiphd, strid, ifail):
            key = string_at(name, namlen[0]).decode("ascii", "replace")
            g = guise[0]
            path = None
            if g == 6:
                hits = [c for c in schema.glob(f"*{key}*")
                        if c.suffix in (".sch_txt", ".s_t")]
                hits = sorted(hits, key=lambda p: (
                    0 if p.suffix == ".sch_txt" else 1, len(p.name)))
                path = hits[0] if hits else None
            else:
                for cand in (Path(key), Path(key + ".x_t")):
                    if cand.is_file():
                        path = cand
                        break
            if not path:
                ifail[0] = 2
                strid[0] = -1
                return
            raw = path.read_bytes()
            is_bin = path.suffix == ".s_t"
            data = raw if is_bin else raw.decode("latin-1", "replace")
            loc = 0
            if not is_bin and skiphd[0] == 1:
                i = data.find("**END_OF_HEADER")
                if i >= 0:
                    nl = data.find("\n", i)
                    loc = nl + 1 if nl >= 0 else i
            sid = self._next_id
            self._next_id += 1
            files[sid] = {"data": data, "loc": loc, "bin": is_bin}
            strid[0] = sid
            ifail[0] = 0

        @CFUNCTYPE(
            None, POINTER(c_int), POINTER(c_int), c_void_p, POINTER(c_int),
            c_void_p, POINTER(c_int), POINTER(c_int), POINTER(c_int),
        )
        def FFOPWR(guise, form, name, namlen, skip, mode, strid, ifail):
            key = string_at(name, namlen[0]).decode("ascii", "replace")
            sid = self._next_id
            self._next_id += 1
            write_files[sid] = bytearray()
            write_paths[sid] = key
            strid[0] = sid
            ifail[0] = 0

        @CFUNCTYPE(
            None, POINTER(c_int), POINTER(c_int), POINTER(c_int), c_void_p,
            POINTER(c_int), POINTER(c_int),
        )
        def FFREAD(guise, strid, nmax, buffer, nactual, ifail):
            f = files.get(strid[0])
            if not f:
                ifail[0] = 99
                nactual[0] = 0
                return
            data, loc, is_bin = f["data"], f["loc"], f["bin"]
            if loc >= len(data):
                nactual[0] = 0
                ifail[0] = 4
                return
            maxn = nmax[0]
            if is_bin:
                n = min(maxn, len(data) - loc)
                memmove(buffer, data[loc:loc + n], n)
                f["loc"] = loc + n
                nactual[0] = n
                ifail[0] = 0
                return
            end = loc
            while end < len(data) and (end - loc) < maxn:
                if data[end] == "\n":
                    end += 1
                    break
                end += 1
            chunk = data[loc:end]
            n = len(chunk)
            memmove(buffer, chunk.encode("latin-1"), n)
            f["loc"] = end
            nactual[0] = n
            ifail[0] = 0

        @CFUNCTYPE(None, POINTER(c_int), POINTER(c_int), POINTER(c_int),
                   c_void_p, POINTER(c_int))
        def FFWRIT(guise, strid, n, buffer, ifail):
            buf = write_files.get(strid[0])
            if buf is None:
                ifail[0] = 14
                return
            buf.extend(string_at(buffer, n[0]))
            ifail[0] = 0

        @CFUNCTYPE(None, POINTER(c_int), POINTER(c_int), POINTER(c_int),
                   POINTER(c_int))
        def FFCLOS(guise, strid, action, ifail):
            if files.pop(strid[0], None) is not None:
                ifail[0] = 0
                return
            buf = write_files.pop(strid[0], None)
            if buf is not None:
                transmit_output[write_paths.pop(strid[0], "")] = bytes(buf)
                ifail[0] = 0
            else:
                ifail[0] = 14

        @CFUNCTYPE(
            None, POINTER(c_int), POINTER(c_int), POINTER(c_int),
            POINTER(c_int), POINTER(c_double), POINTER(c_int),
            POINTER(c_int), POINTER(c_int),
        )
        def GOSGMT(segtyp, ntags, tags, ngeom, geom, nlntp, lntp, ifail):
            try:
                st = segtyp[0]
                ng = ngeom[0]
                nl = nlntp[0]
                lt = [lntp[i] for i in range(nl)] if nl and lntp else []
                nfloat = ng * 3 if st == _SGTPFT else ng
                coords = ([geom[i] for i in range(nfloat)]
                          if nfloat and geom else [])
                segs.append((st, coords, lt))
            except Exception:
                pass
            ifail[0] = 0

        @CFUNCTYPE(
            None, POINTER(c_int), POINTER(c_int), POINTER(c_int),
            POINTER(c_int), POINTER(c_double), POINTER(c_int),
            POINTER(c_int), POINTER(c_int),
        )
        def GOOPSG(*a):
            a[-1][0] = 0

        @CFUNCTYPE(
            None, POINTER(c_int), POINTER(c_int), POINTER(c_int),
            POINTER(c_int), POINTER(c_double), POINTER(c_int),
            POINTER(c_int), POINTER(c_int),
        )
        def GOCLSG(*a):
            a[-1][0] = 0

        @CFUNCTYPE(None, POINTER(c_int))
        def GOPIXL(ifail):
            ifail[0] = 0

        @CFUNCTYPE(None, POINTER(c_int), POINTER(c_int))
        def GOOPPX(a, ifail):
            ifail[0] = 0

        @CFUNCTYPE(None, POINTER(c_int), POINTER(c_int))
        def GOCLPX(a, ifail):
            ifail[0] = 0

        self._cbs = (FSTART, FSTOP, FMALLO, FMFREE, FFOPRD, FFOPWR, FFREAD,
                     FFWRIT, FFCLOS, GOSGMT, GOOPSG, GOCLSG, GOPIXL, GOOPPX,
                     GOCLPX)
        fru = _FRU()
        memset(byref(fru), 0, sizeof(fru))
        for name, fn in [
            ("fstart", FSTART), ("fstop", FSTOP), ("fmallo", FMALLO),
            ("fmfree", FMFREE), ("ffoprd", FFOPRD), ("ffopwr", FFOPWR),
            ("ffclos", FFCLOS), ("ffread", FFREAD), ("ffwrit", FFWRIT),
            ("gosgmt", GOSGMT), ("goopsg", GOOPSG), ("goclsg", GOCLSG),
            ("gopixl", GOPIXL), ("gooppx", GOOPPX), ("goclpx", GOCLPX),
        ]:
            setattr(fru, name, cast(fn, c_void_p))
        pk.PK_SESSION_register_frustrum.argtypes = [POINTER(_FRU)]
        pk.PK_SESSION_register_frustrum.restype = c_int
        rc = pk.PK_SESSION_register_frustrum(byref(fru))
        if rc != 0:
            raise RuntimeError(f"PK_SESSION_register_frustrum failed: {rc}")

    def _start(self) -> None:
        pk = self.pk
        pk.PK_SESSION_start.argtypes = [POINTER(_START)]
        pk.PK_SESSION_start.restype = c_int
        rc = pk.PK_SESSION_start(byref(_START(1, None, 0, 1)))
        if rc != 0:
            raise RuntimeError(f"PK_SESSION_start failed: {rc}")
        # Reverse-engineering workaround: the caller struct version 5 is
        # accepted by the option converter, but the argument checker still
        # compares it against the kernel's own schema constant and would
        # raise PK_ERROR_o_t_version_incorrect (5022).
        pk.PK_SESSION_set_check_arguments.argtypes = [c_int]
        pk.PK_SESSION_set_check_arguments.restype = c_int
        pk.PK_SESSION_set_check_arguments(0)

    # -- part receive ------------------------------------------------------
    def receive_xt(self, xt_bytes: bytes) -> list[int]:
        tmpdir = Path(tempfile.mkdtemp(prefix="cab_ps_"))
        xtp = tmpdir / "part.x_t"
        xtp.write_bytes(xt_bytes)
        key = str(xtp.with_suffix("")).encode()
        pk = self.pk
        pk.PK_PART_receive.restype = c_int
        pk.PK_PART_receive.argtypes = [
            c_char_p, POINTER(_RECV), POINTER(c_int), POINTER(c_void_p)]
        opts = _RECV()
        memset(byref(opts), 0, sizeof(opts))
        opts.o_t_version = 1
        opts.transmit_format = 0  # text
        n = c_int(0)
        parts = c_void_p()
        rc = pk.PK_PART_receive(key, byref(opts), byref(n), byref(parts))
        if rc != 0:
            raise RuntimeError(f"PK_PART_receive failed: {rc}")
        return list(cast(parts, POINTER(c_int * n.value)).contents)

    # -- B-rep 拓扑/几何提取（P1：decode_brep 内核介导）-----------------
    _PK_CLASS_NAMES = {
        2501: "point", 3001: "curve", 4001: "surface",
        5001: "vertex", 5002: "edge", 5003: "loop",
        5004: "face", 5005: "fin", 5006: "body", 5007: "part",
    }

    def _ask_class(self, entity: int) -> int:
        pk = self.pk
        pk.PK_ENTITY_ask_class.restype = c_int
        pk.PK_ENTITY_ask_class.argtypes = [c_int, POINTER(c_int)]
        k = c_int(0)
        if pk.PK_ENTITY_ask_class(int(entity), byref(k)) != 0:
            return -1
        return k.value

    def extract_brep(self, body_tags: list[int]) -> dict:
        """从 body 标签提取 B-rep 拓扑/几何（P1，内核介导）。

        receive_xt / create_solid_block 返回的即 body 标签（class 5006），
        直接 PK_BODY_ask_* 遍历：BODY -> FACE/EDGE/VERTEX，FACE->SURFACE，
        EDGE->CURVE，VERTEX->POINT->coords。返回：
        {bodies, faces, edges, vertices, points[(x,y,z)|None],
         face_surfaces, edge_curves, classes{tag:name}}。
        """
        pk = self.pk

        def ask_arr(fn, entity):
            f = getattr(pk, fn)
            f.restype = c_int
            f.argtypes = [c_int, POINTER(c_int), POINTER(c_void_p)]
            n = c_int(0)
            arr = c_void_p()
            if f(int(entity), byref(n), byref(arr)) != 0 or not n.value:
                return []
            return list(cast(arr, POINTER(c_int * n.value)).contents)

        faces: list[int] = []
        edges: list[int] = []
        vertices: list[int] = []
        for b in body_tags:
            faces += ask_arr("PK_BODY_ask_faces", b)
            edges += ask_arr("PK_BODY_ask_edges", b)
            vertices += ask_arr("PK_BODY_ask_vertices", b)

        pk.PK_VERTEX_ask_point.restype = c_int
        pk.PK_VERTEX_ask_point.argtypes = [c_int, POINTER(c_int)]
        pk.PK_POINT_ask.restype = c_int
        pk.PK_POINT_ask.argtypes = [c_int, POINTER(c_double * 3)]
        points: list = []
        for v in vertices:
            pt = c_int(0)
            if pk.PK_VERTEX_ask_point(int(v), byref(pt)) == 0 and pt.value:
                xyz = (c_double * 3)()
                if pk.PK_POINT_ask(int(pt.value), xyz) == 0:
                    points.append([float(xyz[0]), float(xyz[1]), float(xyz[2])])
                    continue
            points.append(None)

        def ask_ref(fn, entity):
            f = getattr(pk, fn)
            f.restype = c_int
            f.argtypes = [c_int, POINTER(c_int)]
            t = c_int(0)
            if f(int(entity), byref(t)) == 0 and t.value:
                return int(t.value)
            return None

        face_surfaces = [ask_ref("PK_FACE_ask_surf", f) for f in faces]
        edge_curves = [ask_ref("PK_EDGE_ask_curve", e) for e in edges]

        classes: dict[int, str] = {}
        for tag in list(body_tags) + faces + edges + vertices:
            k = self._ask_class(tag)
            classes[int(tag)] = self._PK_CLASS_NAMES.get(k, f"class_{k}")
        for s in face_surfaces:
            if s is not None and s not in classes:
                k = self._ask_class(s)
                classes[s] = self._PK_CLASS_NAMES.get(k, f"class_{k}")
        for c in edge_curves:
            if c is not None and c not in classes:
                k = self._ask_class(c)
                classes[c] = self._PK_CLASS_NAMES.get(k, f"class_{k}")

        return {
            "bodies": [int(b) for b in body_tags],
            "faces": [int(f) for f in faces],
            "edges": [int(e) for e in edges],
            "vertices": [int(v) for v in vertices],
            "points": points,
            "face_surfaces": face_surfaces,
            "edge_curves": edge_curves,
            "classes": classes,
        }

    # -- part transmit（编码：PK_PART → 文本 .x_t）-----------------------
    def transmit_part(self, tag: int, path: str = "") -> bytes:
        """把 PK_PART 编码写回文本 .x_t（PK_PART_transmit，写文件经 frustrum）。"""
        pk = self.pk
        parts = [int(tag)]
        arr = (c_int * len(parts))(*parts)
        opts = _TRANSMIT()
        memset(byref(opts), 0, sizeof(opts))
        opts.o_t_version = 1
        opts.transmit_format = 0  # 0 = text
        pk.PK_PART_transmit.restype = c_int
        pk.PK_PART_transmit.argtypes = [
            c_int, POINTER(c_int), c_char_p, POINTER(_TRANSMIT)]
        key = str(path or "out").encode()
        rc = pk.PK_PART_transmit(len(parts), arr, key, byref(opts))
        if rc != 0:
            raise RuntimeError(f"PK_PART_transmit failed: {rc}")
        # frustrum FFOPWR/FFWRIT 捕获的字节（键 = FFOPWR 收到的 name）
        return self._transmit_output.get(str(path or "out"), b"")

    # -- body boolean（编辑：并/差/交）---------------------------------
    def body_boolean(self, target: int, tools: list[int], op: str) -> list[int]:
        """PK_BODY_boolean_2（6 参数，o_t_version=2）；返回结果 body tag 列表。

        ``op``：unite / subtract / intersect；tool bodies 被内核消耗。
        """
        func = _BOOLEAN_OP_FUNC.get(op)
        if func is None:
            raise ValueError(f"unsupported boolean op: {op}")
        if not tools:
            raise ValueError("no tool bodies")
        pk = self.pk
        opts = _BooleanOpts()
        memset(byref(opts), 0, sizeof(opts))
        opts.o_t_version = 2
        opts.function = func
        opts.fence = PK_boolean_fence_none_c
        opts.check_fa = PK_boolean_check_fa_yes_c
        opts.default_tol = 1.0e-5
        opts.max_tol = 0.0
        track = _TrackR()
        memset(byref(track), 0, sizeof(track))
        res = _BooleanR()
        memset(byref(res), 0, sizeof(res))
        arr = (c_int * len(tools))(*[int(t) for t in tools])
        pk.PK_BODY_boolean_2.restype = c_int
        pk.PK_BODY_boolean_2.argtypes = [
            c_int, c_int, POINTER(c_int), POINTER(_BooleanOpts),
            POINTER(_TrackR), POINTER(_BooleanR)]
        rc = pk.PK_BODY_boolean_2(
            int(target), len(tools), arr, byref(opts), byref(track),
            byref(res))
        if rc != 0:
            raise RuntimeError(f"PK_BODY_boolean_2 failed: {rc}")
        if res.n_bodies <= 0 or not res.bodies:
            raise RuntimeError(
                f"PK_BODY_boolean_2 produced no bodies (result={res.result})")
        return [int(res.bodies[i]) for i in range(res.n_bodies)]


    # -- face delete（编辑：删面）-------------------------------------
    def face_delete(self, face_tags: list[int], *, heal: str = "cap") -> None:
        """PK_FACE_delete_2（cap/shrink 愈合，同 body）。"""
        if not face_tags:
            return
        pk = self.pk
        opts = _FaceDeleteOpts()
        memset(byref(opts), 0, sizeof(opts))
        opts.o_t_version = 1
        opts.update = PK_local_ops_update_default_c
        opts.heal_action = (
            PK_FACE_heal_shrink_c if heal == "shrink" else PK_FACE_heal_cap_c)
        opts.heal_loops = 0
        opts.local_check = 1
        opts.repair_fa_fa = PK_repair_fa_fa_no_c
        opts.track = PK_delete_track_no_c
        track = _TrackR()
        memset(byref(track), 0, sizeof(track))
        arr = (c_int * len(face_tags))(*[int(t) for t in face_tags])
        pk.PK_FACE_delete_2.restype = c_int
        pk.PK_FACE_delete_2.argtypes = [
            c_int, POINTER(c_int), POINTER(_FaceDeleteOpts), POINTER(_TrackR)]
        rc = pk.PK_FACE_delete_2(len(face_tags), arr, byref(opts), byref(track))
        if rc != 0:
            raise RuntimeError(f"PK_FACE_delete_2 failed: {rc}")

    # -- create solid block（编辑：造实体，供布尔/变换测试）---------------
    def create_solid_block(self, size_m, origin_m=(0.0, 0.0, 0.0)) -> int:
        """PK_BODY_create_solid_block → body tag（单位米）。"""
        pk = self.pk
        body = c_int(0)
        ox, oy, oz = (float(v) for v in origin_m)
        if abs(ox) + abs(oy) + abs(oz) < 1e-15:
            pk.PK_BODY_create_solid_block.restype = c_int
            pk.PK_BODY_create_solid_block.argtypes = [
                c_double, c_double, c_double, c_void_p, POINTER(c_int)]
            rc = pk.PK_BODY_create_solid_block(
                float(size_m[0]), float(size_m[1]), float(size_m[2]),
                None, byref(body))
        else:
            ax = _AXIS2()
            ax.location[:] = (ox, oy, oz)
            ax.axis[:] = (0.0, 0.0, 1.0)
            ax.ref_direction[:] = (1.0, 0.0, 0.0)
            pk.PK_BODY_create_solid_block.restype = c_int
            pk.PK_BODY_create_solid_block.argtypes = [
                c_double, c_double, c_double, POINTER(_AXIS2), POINTER(c_int)]
            rc = pk.PK_BODY_create_solid_block(
                float(size_m[0]), float(size_m[1]), float(size_m[2]),
                byref(ax), byref(body))
        if rc != 0 or not body.value:
            raise RuntimeError(f"PK_BODY_create_solid_block failed: {rc}")
        return int(body.value)

    # -- create solid cyl / sphere（P0-3：Cylinder/Sphere 建体）----------
    def create_solid_cyl(self, radius: float, height: float,
                         bottom=(0.0, 0.0, 0.0), direction=(0.0, 0.0, 1.0),
                         ref_direction=None) -> int:
        """PK_BODY_create_solid_cyl(radius, height, basis_set, &body)。

        ``bottom`` 为底面圆心，``direction`` 为轴向（单位化后传入）；
        basis_set.location = 底面圆心（V35 语义，本内核实测一致）。
        传 _AXIS2（9 doubles, location 在前）兼容内核按 PK_VECTOR_t 读取
        的情形（pskernel_user_guide §4 参数检查已关）。
        """
        pk = self.pk
        n = np.asarray(direction, dtype=np.float64)
        nn = float(np.linalg.norm(n))
        if nn < 1e-12:
            raise ValueError("direction must be non-zero")
        n = n / nn
        if ref_direction is None:
            seed = np.array([1.0, 0.0, 0.0])
            if abs(float(n @ seed)) > 0.9:
                seed = np.array([0.0, 1.0, 0.0])
            ref = np.cross(n, np.cross(seed, n))
            ref = ref / float(np.linalg.norm(ref))
        else:
            ref = np.asarray(ref_direction, dtype=np.float64)
            ref = ref / float(np.linalg.norm(ref))
        ax = _AXIS2()
        ax.location[:] = (float(bottom[0]), float(bottom[1]), float(bottom[2]))
        ax.axis[:] = n
        ax.ref_direction[:] = ref
        body = c_int(0)
        pk.PK_BODY_create_solid_cyl.restype = c_int
        pk.PK_BODY_create_solid_cyl.argtypes = [
            c_double, c_double, POINTER(_AXIS2), POINTER(c_int)]
        rc = pk.PK_BODY_create_solid_cyl(
            float(radius), float(height), byref(ax), byref(body))
        if rc != 0 or not body.value:
            raise RuntimeError(f"PK_BODY_create_solid_cyl failed: {rc}")
        return int(body.value)

    def create_solid_sphere(self, radius: float,
                            centre=(0.0, 0.0, 0.0)) -> int:
        """PK_BODY_create_solid_sphere(radius, centre, &body)。"""
        pk = self.pk
        ax = _AXIS2()
        ax.location[:] = (float(centre[0]), float(centre[1]), float(centre[2]))
        ax.axis[:] = (0.0, 0.0, 1.0)
        ax.ref_direction[:] = (1.0, 0.0, 0.0)
        body = c_int(0)
        pk.PK_BODY_create_solid_sphere.restype = c_int
        pk.PK_BODY_create_solid_sphere.argtypes = [
            c_double, POINTER(_AXIS2), POINTER(c_int)]
        rc = pk.PK_BODY_create_solid_sphere(
            float(radius), byref(ax), byref(body))
        if rc != 0 or not body.value:
            raise RuntimeError(f"PK_BODY_create_solid_sphere failed: {rc}")
        return int(body.value)

    def create_solid_cone(self, radius: float, height: float,
                          semi_angle: float, bottom=(0.0, 0.0, 0.0),
                          direction=(0.0, 0.0, 1.0)) -> int:
        """PK_BODY_create_solid_cone(radius, height, semi_angle, basis, &body)。

        V35 签名（pskernel_abi 已映射）：radius(可 0=尖锥) / height(>0) /
        semi_angle(>0, <Pi/2，锥半角，弧度)。basis_set.location = 底面圆心。
        """
        pk = self.pk
        n = np.asarray(direction, dtype=np.float64)
        nn = float(np.linalg.norm(n))
        if nn < 1e-12:
            raise ValueError("direction must be non-zero")
        n = n / nn
        seed = np.array([1.0, 0.0, 0.0])
        if abs(float(n @ seed)) > 0.9:
            seed = np.array([0.0, 1.0, 0.0])
        ref = np.cross(n, np.cross(seed, n))
        ref = ref / float(np.linalg.norm(ref))
        ax = _AXIS2()
        ax.location[:] = (float(bottom[0]), float(bottom[1]), float(bottom[2]))
        ax.axis[:] = n
        ax.ref_direction[:] = ref
        body = c_int(0)
        pk.PK_BODY_create_solid_cone.restype = c_int
        pk.PK_BODY_create_solid_cone.argtypes = [
            c_double, c_double, c_double, POINTER(_AXIS2), POINTER(c_int)]
        rc = pk.PK_BODY_create_solid_cone(
            float(radius), float(height), float(semi_angle),
            byref(ax), byref(body))
        if rc != 0 or not body.value:
            raise RuntimeError(f"PK_BODY_create_solid_cone failed: {rc}")
        return int(body.value)

    def create_solid_torus(self, major_radius: float, minor_radius: float,
                           centre=(0.0, 0.0, 0.0),
                           axis=(0.0, 0.0, 1.0)) -> int:
        """PK_BODY_create_solid_torus(major, minor, basis, &body)。

        V35 签名：major_radius / minor_radius(>0)；basis_set.location =
        环心，axis = 环轴（法向）。
        """
        pk = self.pk
        n = np.asarray(axis, dtype=np.float64)
        nn = float(np.linalg.norm(n))
        if nn < 1e-12:
            raise ValueError("axis must be non-zero")
        n = n / nn
        seed = np.array([1.0, 0.0, 0.0])
        if abs(float(n @ seed)) > 0.9:
            seed = np.array([0.0, 1.0, 0.0])
        ref = np.cross(n, np.cross(seed, n))
        ref = ref / float(np.linalg.norm(ref))
        ax = _AXIS2()
        ax.location[:] = (float(centre[0]), float(centre[1]), float(centre[2]))
        ax.axis[:] = n
        ax.ref_direction[:] = ref
        body = c_int(0)
        pk.PK_BODY_create_solid_torus.restype = c_int
        pk.PK_BODY_create_solid_torus.argtypes = [
            c_double, c_double, POINTER(_AXIS2), POINTER(c_int)]
        rc = pk.PK_BODY_create_solid_torus(
            float(major_radius), float(minor_radius), byref(ax), byref(body))
        if rc != 0 or not body.value:
            raise RuntimeError(f"PK_BODY_create_solid_torus failed: {rc}")
        return int(body.value)

    def create_sheet_rectangle(self, x: float, y: float,
                               origin=(0.0, 0.0, 0.0),
                               normal=(0.0, 0.0, 1.0)) -> int:
        """PK_BODY_create_sheet_rectangle(x, y, basis, &body)。

        V35 签名：x/y = 面内两维尺寸（>0）；basis_set.location = 矩形中心，
        axis = 法向（垂直于矩形的轴）。返回 sheet body tag。
        """
        pk = self.pk
        n = np.asarray(normal, dtype=np.float64)
        nn = float(np.linalg.norm(n))
        if nn < 1e-12:
            raise ValueError("normal must be non-zero")
        n = n / nn
        seed = np.array([1.0, 0.0, 0.0])
        if abs(float(n @ seed)) > 0.9:
            seed = np.array([0.0, 1.0, 0.0])
        ref = np.cross(n, np.cross(seed, n))
        ref = ref / float(np.linalg.norm(ref))
        ax = _AXIS2()
        ax.location[:] = (float(origin[0]), float(origin[1]), float(origin[2]))
        ax.axis[:] = n
        ax.ref_direction[:] = ref
        body = c_int(0)
        pk.PK_BODY_create_sheet_rectangle.restype = c_int
        pk.PK_BODY_create_sheet_rectangle.argtypes = [
            c_double, c_double, POINTER(_AXIS2), POINTER(c_int)]
        rc = pk.PK_BODY_create_sheet_rectangle(
            float(x), float(y), byref(ax), byref(body))
        if rc != 0 or not body.value:
            raise RuntimeError(f"PK_BODY_create_sheet_rectangle failed: {rc}")
        return int(body.value)

    # -- transform（编辑：平移 / 旋转 / 等比缩放 / 镜像）-----------------
    def _apply_transf_tag(self, body: int, tag: int) -> None:
        """把已创建的变换 tag 应用到 body（PK_BODY_transform_2）。"""
        pk = self.pk
        opts = _BodyTransformOpts(1, 1, 1, 0)
        track = (c_byte * 256)()
        res = (c_byte * 256)()
        pk.PK_BODY_transform_2.restype = c_int
        pk.PK_BODY_transform_2.argtypes = [
            c_int, c_int, c_double, POINTER(_BodyTransformOpts),
            c_void_p, c_void_p]
        rc = pk.PK_BODY_transform_2(
            int(body), int(tag), 1e-6, byref(opts), track, res)
        if rc != 0:
            raise RuntimeError(f"PK_BODY_transform_2 failed: {rc}")

    def transform_body(self, body: int, dx: float = 0.0, dy: float = 0.0,
                       dz: float = 0.0) -> None:
        """平移 body：PK_TRANSF_create_translation → PK_BODY_transform_2。

        关键：Cradle pskernel 是 Parasolid V37，``PK_TRANSF_t`` 是 32 位 tag
        （非 V35 的 4x4 矩阵），由 ``PK_TRANSF_create_translation`` 返回，
        ``PK_BODY_transform_2`` 按值接收该 tag。
        """
        pk = self.pk
        disp = (c_double * 3)(float(dx), float(dy), float(dz))
        tag = c_int(0)
        pk.PK_TRANSF_create_translation.restype = c_int
        pk.PK_TRANSF_create_translation.argtypes = [
            POINTER(c_double * 3), POINTER(c_int)]
        rc = pk.PK_TRANSF_create_translation(disp, byref(tag))
        if rc != 0 or not tag.value:
            raise RuntimeError(f"PK_TRANSF_create_translation failed: {rc}")
        self._apply_transf_tag(body, tag.value)

    def rotate_body(self, body: int, *, axis=(0.0, 0.0, 1.0),
                    angle_deg: float = 0.0, position=(0.0, 0.0, 0.0)) -> None:
        """绕 axis 轴旋转 body angle_deg 度（position 为轴上一点）。

        PK_TRANSF_create_rotation(position, axis, angle_radians, &tag)。
        """
        import math
        pk = self.pk
        pos = (c_double * 3)(*position)
        ax = (c_double * 3)(*axis)
        tag = c_int(0)
        pk.PK_TRANSF_create_rotation.restype = c_int
        pk.PK_TRANSF_create_rotation.argtypes = [
            POINTER(c_double * 3), POINTER(c_double * 3), c_double,
            POINTER(c_int)]
        rc = pk.PK_TRANSF_create_rotation(
            pos, ax, math.radians(float(angle_deg)), byref(tag))
        if rc != 0 or not tag.value:
            raise RuntimeError(f"PK_TRANSF_create_rotation failed: {rc}")
        self._apply_transf_tag(body, tag.value)

    def scale_body(self, body: int, *, scale: float = 1.0,
                   centre=(0.0, 0.0, 0.0)) -> None:
        """等比缩放 body（centre 为缩放中心）。

        PK_TRANSF_create_equal_scale(scale, centre, &tag)。
        """
        pk = self.pk
        cen = (c_double * 3)(*centre)
        tag = c_int(0)
        pk.PK_TRANSF_create_equal_scale.restype = c_int
        pk.PK_TRANSF_create_equal_scale.argtypes = [
            c_double, POINTER(c_double * 3), POINTER(c_int)]
        rc = pk.PK_TRANSF_create_equal_scale(float(scale), cen, byref(tag))
        if rc != 0 or not tag.value:
            raise RuntimeError(f"PK_TRANSF_create_equal_scale failed: {rc}")
        self._apply_transf_tag(body, tag.value)

    def reflect_body(self, body: int, *, normal=(1.0, 0.0, 0.0),
                     position=(0.0, 0.0, 0.0)) -> None:
        """关于平面（position + normal）镜像 body。

        PK_TRANSF_create_reflection(position, normal, &tag)。
        """
        pk = self.pk
        pos = (c_double * 3)(*position)
        nrm = (c_double * 3)(*normal)
        tag = c_int(0)
        pk.PK_TRANSF_create_reflection.restype = c_int
        pk.PK_TRANSF_create_reflection.argtypes = [
            POINTER(c_double * 3), POINTER(c_double * 3), POINTER(c_int)]
        rc = pk.PK_TRANSF_create_reflection(pos, nrm, byref(tag))
        if rc != 0 or not tag.value:
            raise RuntimeError(f"PK_TRANSF_create_reflection failed: {rc}")
        self._apply_transf_tag(body, tag.value)

    def body_name(self, tag: int) -> str:
        pk = self.pk
        pk.PK_PART_ask_all_attribs.restype = c_int
        pk.PK_PART_ask_all_attribs.argtypes = [
            c_int, c_char_p, POINTER(c_int), POINTER(c_void_p)]
        pk.PK_ATTRIB_ask_string.restype = c_int
        pk.PK_ATTRIB_ask_string.argtypes = [
            c_int, c_int, POINTER(c_char_p)]
        best = ""
        for aname in (b"SDL/TYSA_NAME", b"SDL/TYSA_UNAME"):
            na = c_int(0)
            attrs = c_void_p()
            rc = pk.PK_PART_ask_all_attribs(tag, aname, byref(na), byref(attrs))
            if rc != 0 or not na.value:
                continue
            for a in cast(attrs, POINTER(c_int * na.value)).contents:
                s = c_char_p()
                if pk.PK_ATTRIB_ask_string(a, 0, byref(s)) == 0 and s.value:
                    raw = s.value
                    try:
                        text = raw.decode("ascii")
                    except UnicodeDecodeError:
                        continue
                    if text and all(32 <= ord(ch) < 127 for ch in text) \
                            and len(text) > len(best):
                        best = text
        return best or f"body_{tag}"

    # -- PK_TOPOL_facet_2 (reverse-engineered table path) -------------------
    def _facet2_call(self, tags: list[int], *,
                     facet_tol: float = DEFAULT_FACET_TOL,
                     facet_angle_deg: float = DEFAULT_FACET_ANGLE_DEG,
                     local_tols: Optional[list[tuple[int, tuple[float, ...]]]]
                     = None) -> Optional["_Facet2Result"]:
        """Build a V5 option block and call PK_TOPOL_facet_2 once.

        ``local_tols`` is a list of ``(topol_tag, tolerance5)`` pairs; the
        kernel overrides the global surface tolerances on exactly those
        faces/bodies (PK_facet_local_tolerances_t, zero entries keep the
        global value).  The result owns kernel memory; decode with
        ``_decode_result``.
        """
        pk = self.pk
        pk.PK_TOPOL_facet_2.restype = c_int
        pk.PK_TOPOL_facet_2.argtypes = [
            c_int, POINTER(c_int), c_void_p, POINTER(_Facet2OptionsV5),
            POINTER(_Facet2Result)]
        opts = _Facet2OptionsV5()
        memset(byref(opts), 0, sizeof(opts))
        opts.control.o_t_version = 5
        opts.control.max_facet_sides = 3
        opts.control.is_surface_plane_tol = 1
        opts.control.surface_plane_tol = max(float(facet_tol), 1e-12)
        opts.control.is_surface_plane_ang = 1
        opts.control.surface_plane_ang = max(
            float(facet_angle_deg) * 0.017453292519943295, 1e-6)
        if local_tols:
            n = len(local_tols)
            tols = (_FacetLocalTolerances * n)()
            topols = (c_int * n)()
            idx = (c_int * n)()
            for i, (tg, t5) in enumerate(local_tols):
                topols[i] = int(tg)
                idx[i] = i
                tols[i] = _FacetLocalTolerances(*t5)
            opts.control.n_local_tols = n
            opts.control.local_tols = cast(tols, c_void_p)
            opts.control.n_topols_with_local_tols = n
            opts.control.topols_with_local_tols = cast(topols, c_void_p)
            opts.control.local_tols_for_topols = cast(idx, c_void_p)
        opts.facet_fin = 1
        opts.fin_data = 1
        opts.data_point_idx = 1
        opts.point_vec = 1
        result = _Facet2Result()
        memset(byref(result), 0, sizeof(result))
        rc = pk.PK_TOPOL_facet_2(
            len(tags), (c_int * len(tags))(*tags), None, byref(opts),
            byref(result))
        if rc != 0 or result.number_of_tables <= 0 or not result.tables:
            return None
        return result

    def _decode_result(self, result, tag: int, name: str) -> Optional[TessPart]:
        """Decode PK_TOPOL_facet_2_r_t tables into a TessPart."""
        tables = cast(result.tables,
                      POINTER(_FacetTable * result.number_of_tables)).contents
        # t.ptr points at the PK_TOPOL_fctab_*_t wrapper {data*, length}.
        data = {}
        for t in tables:
            if t.ptr:
                data[t.fctab] = t.ptr
        if FCTAB_FACET_FIN not in data or FCTAB_FIN_DATA not in data \
                or FCTAB_DATA_POINT_IDX not in data \
                or FCTAB_POINT_VEC not in data:
            return None

        def table_wrapper(ptr: int) -> tuple[int, int]:
            """(data_ptr, length) from a 16-byte PK_TOPOL_fctab_*_t."""
            raw = string_at(ptr, 16)
            return struct.unpack_from("<Qi", raw)

        def pairs(ptr: int, count: int) -> list[tuple[int, int]]:
            """Read ``count`` 8-byte (int, int) lookup-table records."""
            raw = string_at(ptr, count * 8)
            return [(struct.unpack_from("<i", raw, i * 8)[0],
                     struct.unpack_from("<i", raw, i * 8 + 4)[0])
                    for i in range(count)]

        def ints(ptr: int, count: int) -> list[int]:
            """Read ``count`` 4-byte ints from an indexed table."""
            if count <= 0 or not ptr:
                return []
            raw = string_at(ptr, count * 4)
            return list(struct.unpack_from("<%di" % count, raw))

        # facet_fin: lookup table {facet, fin} (8 bytes/record); triangle
        # facets own 3 consecutive fins.  -1 separates hole loops (only with
        # shape=any) and must be skipped.
        ff_ptr, ff_len = table_wrapper(data[FCTAB_FACET_FIN])
        fin_of_facet: dict[int, list[int]] = {}
        for facet, fin in pairs(ff_ptr, ff_len):
            if fin >= 0 and facet >= 0:
                fin_of_facet.setdefault(facet, []).append(fin)

        # fin_data: indexed table data[fin] -> data index.
        fd_ptr, fd_len = table_wrapper(data[FCTAB_FIN_DATA])
        fin_data = ints(fd_ptr, fd_len)
        # data_point_idx: indexed table point[data] -> point_vec index.
        dp_ptr, dp_len = table_wrapper(data[FCTAB_DATA_POINT_IDX])
        point_of_data = ints(dp_ptr, dp_len)
        # point_vec: indexed table of PK_VECTOR_t coordinates.
        pv_ptr, pv_len = table_wrapper(data[FCTAB_POINT_VEC])
        if pv_len <= 0 or not pv_ptr:
            return None
        raw = string_at(pv_ptr, pv_len * 24)
        points = np.frombuffer(
            raw, dtype="<f8", count=pv_len * 3).reshape(-1, 3).copy()

        tris: list[list[int]] = []
        for facet in sorted(fin_of_facet):
            fins = fin_of_facet[facet]
            if len(fins) < 3:
                continue
            verts: list[int] = []
            ok = True
            for f in fins[:3]:
                if not (0 <= f < len(fin_data)):
                    ok = False
                    break
                di = fin_data[f]
                if not (0 <= di < len(point_of_data)):
                    ok = False
                    break
                pi = point_of_data[di]
                if not (0 <= pi < len(points)):
                    ok = False
                    break
                verts.append(pi)
            if ok and len(set(verts)) == 3:
                tris.append(verts)
        if not tris:
            return None
        return TessPart(
            name=name,
            points=points,
            triangles=np.asarray(tris, dtype=np.int32),
            tag=tag,
        )

    def facet2(self, tag: int, *,
               facet_tol: float = DEFAULT_FACET_TOL,
               facet_angle_deg: float = DEFAULT_FACET_ANGLE_DEG,
               local_tols: Optional[list[tuple[int, tuple[float, ...]]]]
               = None) -> Optional[TessPart]:
        """Facet one body through PK_TOPOL_facet_2 and decode tables."""
        result = self._facet2_call(
            [tag], facet_tol=facet_tol, facet_angle_deg=facet_angle_deg,
            local_tols=local_tols)
        if result is None:
            return None
        return self._decode_result(result, tag, self.body_name(tag))

    def body_faces(self, tag: int) -> Optional[list[int]]:
        """Return the PK_FACE tags owned by a body (per-face probing)."""
        pk = self.pk
        pk.PK_BODY_ask_faces.restype = c_int
        pk.PK_BODY_ask_faces.argtypes = [
            c_int, POINTER(c_int), POINTER(c_void_p)]
        n = c_int(0)
        faces = c_void_p()
        rc = pk.PK_BODY_ask_faces(tag, byref(n), byref(faces))
        if rc != 0 or n.value <= 0 or not faces:
            return None
        return list(cast(faces, POINTER(c_int * n.value)).contents)

    def body_vertices(self, tag: int) -> Optional[np.ndarray]:
        """Real B-rep vertex coordinates of a body (PK_FACE_ask_vertices).

        Used by the gridding "All / Representative" vertex detection:
        STpre reads the Parasolid vertices, not the display mesh points.
        """
        faces = self.body_faces(tag)
        if not faces:
            return None
        pk = self.pk
        pk.PK_FACE_ask_vertices.restype = c_int
        pk.PK_FACE_ask_vertices.argtypes = [
            c_int, POINTER(c_int), POINTER(c_void_p)]
        pk.PK_VERTEX_ask_point.restype = c_int
        pk.PK_VERTEX_ask_point.argtypes = [c_int, POINTER(c_double)]
        pts: list[list[float]] = []
        seen: set[int] = set()
        for ft in faces:
            n = c_int(0)
            arr = c_void_p()
            if pk.PK_FACE_ask_vertices(ft, byref(n), byref(arr)) != 0:
                continue
            if n.value <= 0 or not arr:
                continue
            for vt in cast(arr, POINTER(c_int * n.value)).contents:
                if vt in seen:
                    continue
                seen.add(vt)
                xyz = (c_double * 3)()
                if pk.PK_VERTEX_ask_point(vt, xyz) == 0:
                    pts.append([xyz[0], xyz[1], xyz[2]])
        if not pts:
            return None
        return np.asarray(pts, dtype=np.float64)

    def _face_metrics(self, tag: int, *, facet_tol: float,
                      facet_angle_deg: float
                      ) -> Optional[tuple[int, float, float, np.ndarray]]:
        """Facet one face at base tolerances; return
        ``(n_facets, area, max_intra_face_dihedral_deg, points)``."""
        result = self._facet2_call(
            [tag], facet_tol=facet_tol, facet_angle_deg=facet_angle_deg)
        if result is None:
            return None
        part = self._decode_result(result, tag, "")
        if part is None or len(part.triangles) == 0:
            return None
        pts = part.points
        tris = part.triangles.astype(np.int64)
        a = pts[tris[:, 0]]
        b = pts[tris[:, 1]]
        c = pts[tris[:, 2]]
        nrm = np.cross(b - a, c - a)
        ln = np.linalg.norm(nrm, axis=1)
        ln[ln < 1e-300] = 1.0
        nrm = nrm / ln[:, None]
        area = float(0.5 * ln.sum())
        edges: dict[tuple[int, int], list[int]] = {}
        for i, (t0, t1, t2) in enumerate(tris.tolist()):
            for e in ((t0, t1), (t1, t2), (t2, t0)):
                key = (min(e), max(e))
                edges.setdefault(key, []).append(i)
        max_ang = 0.0
        for idxs in edges.values():
            if len(idxs) < 2:
                continue
            for i in range(len(idxs)):
                for j in range(i + 1, len(idxs)):
                    d = float(np.clip(
                        np.dot(nrm[idxs[i]], nrm[idxs[j]]), -1.0, 1.0))
                    ang = float(np.degrees(np.arccos(d)))
                    if ang > max_ang:
                        max_ang = ang
        return len(part.triangles), area, max_ang, pts

    def _adaptive_facet2(self, tag: int, *,
                         facet_tol: float = DEFAULT_FACET_TOL,
                         facet_angle_deg: float = DEFAULT_FACET_ANGLE_DEG,
                         refine_angle_deg: float = DEFAULT_REFINE_ANGLE_DEG,
                         refine_tol: float = DEFAULT_REFINE_TOL,
                         smooth_angle_deg: float = DEFAULT_SMOOTH_ANGLE_DEG,
                         min_rel_area: float = DEFAULT_MIN_REL_AREA,
                         min_face_facets: int = DEFAULT_MIN_FACE_FACETS
                         ) -> Optional[TessPart]:
        """Adaptive PK_TOPOL_facet_2 with per-face local tolerances.

        Strategy (preventive, not post-hoc):
          1. Probe every PK_FACE of the body at the base tolerances.
          2. For each face measure facet count, area and the *intra-face*
             maximum dihedral angle (edges shared inside the same face only,
             so sharp model edges between faces do not pollute the metric).
          3. Select faces whose mesh is angularly coarse (dihedral above
             ``smooth_angle_deg``) AND physically large enough (area >=
             ``min_rel_area`` x body bbox area, at least ``min_face_facets``
             facets).  Tiny fillets stay cheap; large curved faces get a
             tighter local ``surface_plane_ang/tol``.
          4. One final body-level facet_2 call attaches the local tolerance
             sets to exactly those faces (PK_facet_local_tolerances_t).

        Falls back to a plain body facet_2 when probing is not possible.
        """
        faces = self.body_faces(tag)
        if not faces:
            return self.facet2(
                tag, facet_tol=facet_tol, facet_angle_deg=facet_angle_deg)
        rows: list[tuple[int, int, float, float]] = []
        lo = np.full(3, np.inf)
        hi = np.full(3, -np.inf)
        for ft in faces:
            m = self._face_metrics(
                ft, facet_tol=facet_tol, facet_angle_deg=facet_angle_deg)
            if m is None:
                return self.facet2(
                    tag, facet_tol=facet_tol,
                    facet_angle_deg=facet_angle_deg)
            nf, area, ang, pts = m
            rows.append((ft, nf, area, ang))
            pmin = pts.min(0)
            pmax = pts.max(0)
            lo = np.minimum(lo, pmin)
            hi = np.maximum(hi, pmax)
        d = hi - lo
        bbox_area = 2.0 * (d[0] * d[1] + d[1] * d[2] + d[2] * d[0])
        if bbox_area <= 0:
            bbox_area = 1.0
        sel = [
            (ft, nf) for ft, nf, area, ang in rows
            if ang > float(smooth_angle_deg)
            and area >= float(min_rel_area) * bbox_area
            and nf >= int(min_face_facets)
        ]
        if not sel:
            return self.facet2(
                tag, facet_tol=facet_tol, facet_angle_deg=facet_angle_deg)
        local = [
            (ft, (0.0, 0.0, 0.0, float(refine_tol),
                  float(refine_angle_deg) * 0.017453292519943295))
            for ft, _nf in sel
        ]
        return self.facet2(
            tag, facet_tol=facet_tol, facet_angle_deg=facet_angle_deg,
            local_tols=local)

    def facet_body_adaptive(self, tag: int, **kw) -> Optional[TessPart]:
        """Adaptive facet_2, with the GO path as final fallback."""
        part = self._adaptive_facet2(tag, **kw)
        if part is not None:
            return part
        return self.facet_go(
            tag, facet_tol=kw.get("facet_tol", DEFAULT_FACET_TOL),
            facet_angle_deg=kw.get("facet_angle_deg",
                                   DEFAULT_FACET_ANGLE_DEG))

    # -- PK_TOPOL_render_facet GO fallback ---------------------------------
    def facet_go(self, tag: int, *,
                 facet_tol: float = DEFAULT_FACET_TOL,
                 facet_angle_deg: float = DEFAULT_FACET_ANGLE_DEG
                 ) -> Optional[TessPart]:
        pk = self.pk
        self._segs.clear()

        class _GoOpts(Structure):
            _fields_ = [
                ("o_t_version", c_int), ("go_normals", c_int),
                ("go_parameters", c_int), ("go_curvatures", c_int),
                ("go_edges", c_int), ("go_strips", c_int),
                ("go_max_facets_per_strip", c_int),
                ("go_interleaved", c_int), ("split_strips", c_int),
                ("consistent_parms", c_int),
            ]

        class _MeshOpts(Structure):
            _fields_ = [
                ("o_t_version", c_int),
                ("shape", c_int), ("match", c_int), ("density", c_int),
                ("cull", c_int), ("n_loops", c_int), ("loops", c_void_p),
                ("max_facet_sides", c_int),
                ("is_min_facet_width", c_int), ("min_facet_width", c_double),
                ("is_max_facet_width", c_int), ("max_facet_width", c_double),
                ("is_curve_chord_tol", c_int), ("curve_chord_tol", c_double),
                ("is_curve_chord_max", c_int), ("curve_chord_max", c_double),
                ("is_curve_chord_ang", c_int), ("curve_chord_ang", c_double),
                ("is_surface_plane_tol", c_int),
                ("surface_plane_tol", c_double),
                ("is_surface_plane_ang", c_int),
                ("surface_plane_ang", c_double),
                ("is_facet_plane_tol", c_int), ("facet_plane_tol", c_double),
                ("is_facet_plane_ang", c_int), ("facet_plane_ang", c_double),
                ("is_local_density_tol", c_int),
                ("local_density_tol", c_double),
                ("is_local_density_ang", c_int),
                ("local_density_ang", c_double),
                ("degen", c_int), ("n_view_directions", c_int),
                ("view_directions", c_void_p), ("n_local_tols", c_int),
                ("local_tols", c_void_p),
                ("n_topols_with_local_tols", c_int),
                ("topols_with_local_tols", c_void_p),
                ("local_tols_for_topols", c_void_p),
                ("ignore", c_int), ("ignore_value", c_double),
                ("ignore_scope", c_int), ("wire_edges", c_int),
                ("incremental_facetting", c_int),
                ("incremental_method", c_int),
                ("incremental_propagation", c_int),
                ("incremental_transformation", c_int),
                ("incremental_refinement", c_int),
                ("incremental_report", c_int),
                ("inflect", c_int), ("quality", c_int),
                ("vertices_on_planar", c_int), ("respect_offset", c_int),
                ("n_bodies_with_scales", c_int),
                ("bodies_with_scales", c_void_p),
                ("scale_factors", c_void_p),
                ("n_viewports", c_int), ("viewports", c_void_p),
            ]

        class _RenderOpts(Structure):
            _fields_ = [("control", _MeshOpts), ("go_option", _GoOpts)]

        opts = _RenderOpts()
        opts.control.o_t_version = 1
        opts.go_option.o_t_version = 1
        opts.control.max_facet_sides = 3
        opts.control.is_surface_plane_tol = 1
        opts.control.surface_plane_tol = max(float(facet_tol), 1e-12)
        opts.control.is_surface_plane_ang = 1
        opts.control.surface_plane_ang = max(
            float(facet_angle_deg) * 0.017453292519943295, 1e-6)
        pk.PK_TOPOL_render_facet.restype = c_int
        pk.PK_TOPOL_render_facet.argtypes = [
            c_int, POINTER(c_int), c_void_p, c_void_p,
            POINTER(_RenderOpts)]
        rc = pk.PK_TOPOL_render_facet(
            1, (c_int * 1)(tag), None, None, byref(opts))
        if rc != 0:
            return None
        pts: list[list[float]] = []
        tris: list[list[int]] = []
        index: dict[tuple[float, float, float], int] = {}

        def vid(x, y, z):
            key = (round(x, 12), round(y, 12), round(z, 12))
            i = index.get(key)
            if i is None:
                i = len(pts)
                index[key] = i
                pts.append([x, y, z])
            return i

        for st, coords, lt in self._segs:
            if st != _SGTPFT or len(coords) < 9:
                continue
            if len(lt) > 2 and lt[2] != 1:
                continue
            nverts = lt[3] if len(lt) > 3 else len(coords) // 3
            if nverts < 3:
                continue
            v0 = vid(coords[0], coords[1], coords[2])
            prev = vid(coords[3], coords[4], coords[5])
            for k in range(2, nverts):
                cur = vid(coords[3 * k], coords[3 * k + 1],
                          coords[3 * k + 2])
                tris.append([v0, prev, cur])
                prev = cur
        if not tris:
            return None
        return TessPart(
            name=self.body_name(tag),
            points=np.asarray(pts, dtype=np.float64),
            triangles=np.asarray(tris, dtype=np.int32),
            tag=tag,
        )

    def facet_body(self, tag: int, **kw) -> Optional[TessPart]:
        part = self.facet2(tag, **kw)
        if part is None:
            part = self.facet_go(tag, **kw)
        return part


def _get_session() -> _PsSession:
    global _session
    if _session is not None:
        return _session
    prog = find_cradle_programs()
    if prog is None:
        raise RuntimeError(
            "Cradle pskernel.dll not found; set CRADLE_PROGRAMS")
    _session = _PsSession(prog)
    return _session


def tessellate_xt_file(path: str | Path, **kw) -> list[TessPart]:
    return tessellate_xt(Path(path).read_bytes(), **kw)


def transmit_xt(xt_bytes: bytes, tag: Optional[int] = None) -> bytes:
    """接收文本 .x_t，把首个（或指定）body 编码写回文本 .x_t 字节。

    这是 :meth:`_PsSession.receive_xt` + PK_PART_transmit 的编码 round-trip
    封装：输入 x_t → PK_PART_receive → PK_PART_transmit → 输出 x_t。
    """
    sess = _get_session()
    tags = sess.receive_xt(xt_bytes)
    if not tags:
        raise RuntimeError("transmit_xt: no bodies received")
    t = tags[0] if tag is None else int(tag)
    return sess.transmit_part(t, "out")


def decode_brep(xt_bytes: bytes) -> dict:
    """P1：接收 x_t → 提取 B-rep 拓扑/几何（内核介导）。

    接收的 body（class 5006）直接 PK_BODY_ask_faces/edges/vertices 遍历，
    VERTEX→POINT→coords、FACE→SURFACE、EDGE→CURVE。返回 extract_brep 结果
    （{bodies, faces, edges, vertices, points, face_surfaces, edge_curves,
    classes}）。
    """
    sess = _get_session()
    bodies = sess.receive_xt(xt_bytes)
    if not bodies:
        raise RuntimeError("decode_brep: no bodies received")
    return sess.extract_brep(bodies)

def boolean_bodies(xt_bytes: bytes, target_index: int = 0,
                   tools_indices: Optional[list[int]] = None,
                   op: str = "unite") -> tuple[list[int], list[int]]:
    """接收 x_t → PK_BODY_boolean_2 → 返回 (结果 tags, 原 body tags)。"""
    sess = _get_session()
    tags = sess.receive_xt(xt_bytes)
    if not tags:
        raise RuntimeError("no bodies received")
    tools = [tags[i] for i in (tools_indices or list(range(1, len(tags))))]
    res = sess.body_boolean(tags[target_index], tools, op)
    return res, tags


def delete_faces(face_tags: list[int], *, heal: str = "cap") -> None:
    """PK_FACE_delete_2（cap/shrink 愈合）。"""
    sess = _get_session()
    sess.face_delete(face_tags, heal=heal)


def translate_body(body: int, dx: float = 0.0, dy: float = 0.0,
                  dz: float = 0.0) -> None:
    """PK_TRANSF_create_translation + PK_BODY_transform_2 平移 body。"""
    sess = _get_session()
    sess.transform_body(body, dx, dy, dz)


def rotate_body(body: int, *, axis=(0.0, 0.0, 1.0), angle_deg: float = 0.0,
                position=(0.0, 0.0, 0.0)) -> None:
    """PK_TRANSF_create_rotation + PK_BODY_transform_2 旋转 body。"""
    sess = _get_session()
    sess.rotate_body(body, axis=axis, angle_deg=angle_deg, position=position)


def scale_body(body: int, *, scale: float = 1.0,
               centre=(0.0, 0.0, 0.0)) -> None:
    """PK_TRANSF_create_equal_scale + PK_BODY_transform_2 等比缩放 body。"""
    sess = _get_session()
    sess.scale_body(body, scale=scale, centre=centre)


def reflect_body(body: int, *, normal=(1.0, 0.0, 0.0),
                 position=(0.0, 0.0, 0.0)) -> None:
    """PK_TRANSF_create_reflection + PK_BODY_transform_2 镜像 body。"""
    sess = _get_session()
    sess.reflect_body(body, normal=normal, position=position)


def tessellate_xt(xt_bytes: bytes, *, adaptive: bool = False,
                  **kw) -> list[TessPart]:
    """Tessellate every body in a text ``.x_t`` byte stream.

    Uses the reverse-engineered ``PK_TOPOL_facet_2`` table path (the same
    one STpre uses), with a ``PK_TOPOL_render_facet`` GO fallback per body.
    Pass ``adaptive=True`` to enable per-face local-tolerance refinement of
    large, angularly-coarse curved faces (see ``facet_body_adaptive``); the
    default stays on the plain STpre-style tolerances.
    """
    sess = _get_session()
    tags = sess.receive_xt(xt_bytes)
    out: list[TessPart] = []
    for tag in tags:
        if adaptive:
            part = sess.facet_body_adaptive(tag, **kw)
        else:
            part = sess.facet_body(tag, **kw)
        if part is not None and part.triangles.size:
            out.append(part)
    return out


def write_obj(path: str | Path, parts: list[TessPart]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        base = 0
        for part in parts:
            f.write(f"o {part.name}\n")
            for x, y, z in part.points:
                f.write(f"v {x:.12g} {y:.12g} {z:.12g}\n")
            for a, b, c in part.triangles:
                f.write(f"f {a + 1 + base} {b + 1 + base} {c + 1 + base}\n")
            base += len(part.points)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Tessellate a Parasolid .x_t via pskernel PK_TOPOL_facet_2 "
                    "(reverse-engineered STpre node path).")
    ap.add_argument("xt", type=Path, help="input text .x_t file")
    ap.add_argument("--obj", type=Path, default=None,
                    help="optional Wavefront OBJ output")
    ap.add_argument("--tol", type=float, default=DEFAULT_FACET_TOL,
                    help="surface facet distance tolerance")
    ap.add_argument("--angle", type=float, default=DEFAULT_FACET_ANGLE_DEG,
                    help="surface facet angle tolerance (degrees)")
    ap.add_argument("--adaptive", action="store_true",
                    help="per-face adaptive refinement of large curved faces")
    ap.add_argument("--refine-angle", type=float,
                    default=DEFAULT_REFINE_ANGLE_DEG,
                    help="local angle tolerance for refined faces (degrees)")
    args = ap.parse_args()
    parts = tessellate_xt_file(
        args.xt, facet_tol=args.tol, facet_angle_deg=args.angle,
        adaptive=args.adaptive, refine_angle_deg=args.refine_angle)
    for p in parts:
        print(f"{p.name}: {len(p.points)} nodes, {len(p.triangles)} triangles")
    if args.obj:
        write_obj(args.obj, parts)
        print(f"wrote {args.obj}")


if __name__ == "__main__":
    main()
