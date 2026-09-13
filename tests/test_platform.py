"""3.4 平台与依赖限制：LZMS 跨平台回退 + 仓库内 gph 轻量统计。"""

import sys

import numpy as np
import pytest

import gphstats
import pph_parser
import sctsnapshot


BOX_GPH = r"tests\box\meshinggroup1.gph"


class _FakeLib:
    """模拟 wimlib 动态库对象（ctypes argtypes/restype 赋值无副作用）。"""

    def __init__(self, **symbols):
        self._symbols = symbols
        self.calls = []

    def __getattr__(self, name):
        if name in self._symbols:
            return self._symbols[name]
        raise AttributeError(name)


def _old_api_lib():
    def wimlib_decompress(compressed, comp_size, out, unc_size, ctype):
        # 模拟成功：把输入原样写入输出（测试仅关心参数与调用路径）
        out[:len(compressed)] = compressed
        return 0

    return _FakeLib(wimlib_decompress=wimlib_decompress)


def _new_api_lib():
    def wimlib_create_decompressor(ctype, max_block_size, handle_ptr):
        return 0  # 真实 ctypes 库内部会回填句柄；测试桩不校验内容

    def wimlib_decompress_with_decompressor(handle, comp, comp_size, out, unc_size):
        out[:len(comp)] = comp
        return 0

    def wimlib_free_decompressor(handle):
        return None

    return _FakeLib(
        wimlib_create_decompressor=wimlib_create_decompressor,
        wimlib_decompress_with_decompressor=wimlib_decompress_with_decompressor,
        wimlib_free_decompressor=wimlib_free_decompressor,
    )


@pytest.fixture
def fake_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    return monkeypatch


# ── gph 内建统计 ────────────────────────────────────────────────────────────

def test_gphstats_box_matches_reference_counts():
    with gphstats.open_buffer(BOX_GPH) as data:
        s = gphstats.summarize(data)
    assert s["links"]["n_faces"] == 3168
    assert s["links"]["n_cells"] == 944
    assert s["links"]["boundary_faces"] == 600
    assert (s["links"]["npe_min"], s["links"]["npe_max"]) == (4, 6)
    assert s["links"]["polyhedral"] is True
    assert s["n_cells"] == 944
    assert s["cvol_unique"] == [1]
    assert s["n_vertices"] == 1305
    assert s["surface_regions"] == [("open", 600), ("@PartSurface_Part", 600)]
    assert s["volume_regions"] == ["FluidRegion"]
    assert [(n, gphstats.format_part_cvol_spec(p)) for n, p in s["parts"]] == [
        ("Part", "1")
    ]


def test_gphstats_missing_sections_return_defaults():
    empty = b"\x00" * 64
    assert gphstats.links_summary(empty) is None
    assert gphstats.cvol_ids(empty) is None
    assert gphstats.nodes_vertex_count(empty) == (None, "")
    assert gphstats.surface_regions_summary(empty) == []
    assert gphstats.string_list(empty, "LS_VolumeRegions") == []
    assert gphstats.parts_summary(empty) == []


def test_gphstats_sections_roundtrip_with_crdlfld():
    import crdlfld

    with open(BOX_GPH, "rb") as f:
        data = f.read()
    names = [s.name for s in crdlfld.scan_sections(data)]
    for expected in ("LS_Links", "LS_Nodes", "LS_Parts", "LS_SurfaceRegions"):
        assert expected in names


# ── LZMS 回退调度 ──────────────────────────────────────────────────────────

def test_lzms_available_false_without_backend(fake_linux, monkeypatch):
    monkeypatch.setattr(sctsnapshot, "_wimlib_library", lambda: None)
    assert sctsnapshot.lzms_available() is False


def test_lzms_fallback_old_wimlib_api(fake_linux, monkeypatch):
    lib = _old_api_lib()
    monkeypatch.setattr(sctsnapshot, "_wimlib_library", lambda: lib)
    out = sctsnapshot.lzms_decompress(b"abcdef", 6)
    assert out == b"abcdef"
    assert sctsnapshot.lzms_available() is True


def test_lzms_fallback_new_wimlib_api(fake_linux, monkeypatch):
    lib = _new_api_lib()
    monkeypatch.setattr(sctsnapshot, "_wimlib_library", lambda: lib)
    out = sctsnapshot.lzms_decompress(b"hello", 5)
    assert out == b"hello"


def test_lzms_fallback_requires_uncompressed_size(fake_linux, monkeypatch):
    monkeypatch.setattr(sctsnapshot, "_wimlib_library", lambda: None)
    with pytest.raises(RuntimeError):
        sctsnapshot.lzms_decompress(b"not an lzms stream")


def test_lzms_fallback_after_cabinet_failure(fake_linux, monkeypatch):
    # win32 平台但 cabinet.dll 加载失败 → 回退 wimlib
    monkeypatch.setattr(sys, "platform", "win32")
    lib = _old_api_lib()
    monkeypatch.setattr(sctsnapshot, "_wimlib_library", lambda: lib)
    real_windll = sys.modules["ctypes"].WinDLL

    def fail_windll(name):
        raise OSError("no cabinet")

    monkeypatch.setattr(sys.modules["ctypes"], "WinDLL", fail_windll)
    out = sctsnapshot.lzms_decompress(b"data", 4)
    assert out == b"data"
    sys.modules["ctypes"].WinDLL = real_windll


def test_cabinet_backend_still_works_on_windows():
    if sys.platform != "win32":
        pytest.skip("cabinet.dll 仅 Windows")
    import zipfile

    with zipfile.ZipFile(r"box.pph") as z:
        data = z.read("main.sctsnapshot")
    i = data.find(b"ZIPBODYBYTES")
    ln = int.from_bytes(data[i + 16:i + 20], "little")
    payload = data[i + 20:i + 20 + ln]
    out = sctsnapshot.lzms_decompress(payload)
    assert len(out) == 7667


# ── pph_parser 的 gph 降级路径 ─────────────────────────────────────────────

def test_try_gph_deep_uses_builtin_fallback(monkeypatch):
    monkeypatch.setattr(pph_parser, "_GPH_DECODING_CANDIDATES",
                        [__import__("pathlib").Path("nonexistent")])
    lines = pph_parser._try_gph_deep(BOX_GPH)
    assert lines is not None
    joined = "\n".join(lines)
    assert "网格: 3,168 面 / 944 单元 / 1,305 顶点" in joined
    assert "内置轻量统计" in joined
    assert "边界面: 600" in joined
    assert "面区域: open(600)" in joined
