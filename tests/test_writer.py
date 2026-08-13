"""3.5 写端：LZMS 压缩 / Blowfish 加密 / ZIP 容器 round-trip。"""

import os
import tempfile
import unittest
import zipfile

import pytest

import pph_parser
import pphwriter
import pphxml
import sctsnapshot


BOX_PPH = r"box.pph"


def _load_snap(pph_path: str) -> sctsnapshot.SctSnapshot:
    with zipfile.ZipFile(pph_path) as z:
        raw = z.read("main.sctsnapshot")
    tmp = os.path.join(tempfile.gettempdir(), "snap_writer.bin")
    with open(tmp, "wb") as f:
        f.write(raw)
    return sctsnapshot.SctSnapshot.load(tmp)


@pytest.mark.skipif(os.name != "nt", reason="LZMS 压缩需 Windows cabinet.dll")
def test_lzms_compress_roundtrip():
    plain = bytes(range(256)) * 40 + b"PPH writer round-trip" * 100
    stream = pphwriter.lzms_compress(plain)
    hdr = pphwriter.parse_lzms_header(stream)
    assert hdr["uncompressed_size"] == len(plain)
    assert hdr["magic"] == pphwriter.LZMS_MAGIC
    # 与读取端 ZipBlob.parse 兼容
    blob = sctsnapshot.ZipBlob.parse(stream)
    assert blob.uncompressed_size == len(plain)
    assert blob.decompress() == plain


@pytest.mark.skipif(os.name != "nt", reason="LZMS 压缩需 Windows cabinet.dll")
def test_lzms_compress_nonempty_payload():
    # 输出必须是"真压缩"（流总长 < 明文长），不是透传
    plain = bytes(range(256)) * 200
    stream = pphwriter.lzms_compress(plain)
    assert len(stream) < len(plain)


def test_pkbody3_encrypt_decrypt_roundtrip():
    snap = _load_snap(BOX_PPH)
    zipblob = snap.bodies()[0]["zip"]
    body = zipblob.decompress_body()
    plain = body.decrypt()
    # ECB 确定性 + 原始填充即零字节 → 再加密与原始包装逐字节一致
    re_wrapped = pphwriter.encrypt_pkbody3(plain)
    assert re_wrapped == zipblob.decompress()
    body2 = sctsnapshot.PKBody3.parse(re_wrapped)
    assert body2.data == body.data
    assert body2.logical_size == body.logical_size
    assert body2.decrypt() == plain


def test_pkbody3_wrapper_without_trailer():
    # 8 倍数长度：无零填充块 → "尾标"不出现
    plain = b"hello parasolid" * 8  # 128 B，8 的倍数
    wrapped = pphwriter.encrypt_pkbody3(plain)
    body = sctsnapshot.PKBody3.parse(wrapped)
    assert body.checksum is None
    assert body.pad == b""
    assert body.decrypt() == plain
    assert len(body.data) == len(plain)


def test_pkbody3_padding_block_artifact():
    # 非 8 倍数长度：末块为 E(0^8) 的密文 → checksum/pad 是密文碎片
    plain = b"\x00" * 3  # 3 B 零 + 5 B 零填充 → 整块为 E(0^8)
    wrapped = pphwriter.encrypt_pkbody3(plain)
    body = sctsnapshot.PKBody3.parse(wrapped)
    assert body.logical_size == 3
    assert len(body.data) == 8
    assert body.checksum == sctsnapshot.PKBODY3_TRAILER_MARK
    assert body.pad == b"\xb1"
    assert body.decrypt() == plain


def test_clone_pph_members_identical():
    with tempfile.TemporaryDirectory() as tmp:
        dst = os.path.join(tmp, "clone.pph")
        pphwriter.clone_pph(BOX_PPH, dst)
        src_arch = pph_parser.PphArchive.open(BOX_PPH)
        dst_arch = pph_parser.PphArchive.open(dst)
        assert [(m.name, m.size) for m in src_arch.members] == [
            (m.name, m.size) for m in dst_arch.members]
        # 每个成员字节一致
        for m in src_arch.members:
            assert dst_arch.read_member(m.name) == src_arch.read_member(m.name)


def test_clone_pph_appends_new_members():
    """原生 Execute 空工程写回：override 键不存在时作为新成员追加。"""
    with tempfile.TemporaryDirectory() as tmp:
        dst = os.path.join(tmp, "append.pph")
        pphwriter.clone_pph(
            BOX_PPH, dst,
            {"meshinggroup1.oct": b"OCT", "meshinggroup1.gph": b"GPH"})
        arch = pph_parser.PphArchive.open(dst)
        names = {m.name for m in arch.members}
        assert "meshinggroup1.oct" in names
        assert "meshinggroup1.gph" in names
        assert arch.read_member("meshinggroup1.oct") == b"OCT"
        assert arch.read_member("meshinggroup1.gph") == b"GPH"


def test_rewrite_main_xml_roundtrip_and_modify():
    with zipfile.ZipFile(BOX_PPH) as z:
        xml_orig = z.read("main.xml").decode("utf-8")
    san = pphxml.sanitize_scflow_xml(xml_orig)
    root = pphxml.ET.fromstring(san)
    back = pphxml.serialize_main_xml(root)
    # 结构级 round-trip：重新 sanitize + 解析与原树同构
    root2 = pphxml.ET.fromstring(pphxml.sanitize_scflow_xml(back))
    assert [c.tag for c in root2] == [c.tag for c in root]

    # 修改版本号并写回新 pph，再解析验证
    for node in root.iter("version"):
        node.text = "9999.99999.99999999"
    modified = pphxml.serialize_main_xml(root)
    with tempfile.TemporaryDirectory() as tmp:
        dst = os.path.join(tmp, "modified.pph")
        pphwriter.rewrite_pph(BOX_PPH, dst, {"main.xml": modified.encode("utf-8")})
        arch = pph_parser.PphArchive.open(dst)
        new_xml = arch.read_member("main.xml").decode("utf-8")
        assert "9999.99999.99999999" in new_xml
        assert "5225.20302.20251223" not in new_xml


def test_full_snapshot_blob_rebuild():
    """解压 → 解密 → 加密 → 再压缩 → 再解压，完整 PKBody3 闭环。"""
    if os.name != "nt":
        pytest.skip("LZMS 压缩需 Windows cabinet.dll")
    snap = _load_snap(BOX_PPH)
    zipblob = snap.bodies()[0]["zip"]
    body = zipblob.decompress_body()
    plain = body.decrypt()
    wrapped = pphwriter.encrypt_pkbody3(plain)
    stream = pphwriter.lzms_compress(wrapped)
    blob = sctsnapshot.ZipBlob.parse(stream)
    body2 = blob.decompress_body()
    assert body2.data == body.data
    assert body2.logical_size == body.logical_size
    assert body2.decrypt() == plain
    # 新 LZMS 流解压后与原始明文负载一致（含包装头）
    assert blob.decompress() == zipblob.decompress()


if __name__ == "__main__":
    unittest.main()
