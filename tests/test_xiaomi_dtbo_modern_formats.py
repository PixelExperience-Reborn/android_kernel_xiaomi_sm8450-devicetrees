"""Strict manufacturer DTBO metadata tests from published AOSP mkdtboimg specs.

All DTB inputs are intentionally synthetic. These tests never incorporate
LineageOS or Xiaomi-proprietary firmware/DSI commands.
"""
import gzip
import struct
import sys
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_xiaomi_stock_dtbo import parse_android_dtbo  # noqa: E402

FDT_MAGIC = 0xD00DFEED
DTBO_MAGIC = 0xD7B7AB1E


def synthetic_fdt():
    structure = struct.pack(">4I", 1, 0, 2, 9)
    total = 40 + 16 + len(structure)
    return struct.pack(">10I", FDT_MAGIC, total, 56, total, 40,
                       17, 16, 0, 0, len(structure)) + b"\x00" * 16 + structure


def dtbo_image(version, payload, *, flags=0, board_id=530, revision=4,
               custom=None, entry_size_override=None, page_size=4096):
    if version == 0:
        customs = list(custom if custom is not None else [10, 11, 12, 13])
        if len(customs) != 4:
            raise ValueError("synthetic test expects 4 custom fields for v0")
        entry_data = [len(payload), 32 + 32, board_id, revision, *customs]
        size = 32
    elif version == 1:
        customs = list(custom if custom is not None else [20, 21, 22])
        if len(customs) != 3:
            raise ValueError("synthetic test expects 3 custom fields for v1")
        entry_data = [len(payload), 32 + 32, board_id, revision, flags, *customs]
        size = 32
    elif version == 2:
        customs = list(custom if custom is not None else range(11))
        if len(customs) != 11:
            raise ValueError("synthetic test expects 11 custom fields for v2")
        entry_data = [len(payload), 32 + 64, board_id, revision, flags, *customs]
        size = 64
    else:
        raise ValueError("unknown synthetic version")
    header = struct.pack(">8I", DTBO_MAGIC, 32 + size + len(payload),
                         32, entry_size_override or size, 1, 32,
                         page_size, version)
    entry = struct.pack(">" + str(len(entry_data)) + "I", *entry_data)
    return header + entry + payload


class XiaomiModernAndroidDtboTests(unittest.TestCase):
    def test_v0_custom_fields_preserved_for_bootloader_sku_audit(self):
        image = dtbo_image(0, synthetic_fdt(), custom=[0xE, 0, 7, 0])
        entries = parse_android_dtbo(image, with_metadata=True)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["custom_fields"], [0xE, 0, 7, 0])
        self.assertEqual(entries[0]["id"], 530)
        self.assertEqual(entries[0]["revision"], 4)
        self.assertEqual(entries[0]["table_page_size"], 4096)
        self.assertEqual(entries[0]["table_version"], 0)
        self.assertEqual(entries[0]["fdt"], synthetic_fdt())
        self.assertEqual(parse_android_dtbo(image)[0][3], synthetic_fdt())

    def test_v1_uncompressed_custom_fields(self):
        output = parse_android_dtbo(dtbo_image(1, synthetic_fdt()), with_metadata=True)
        self.assertEqual(output[0]["table_version"], 1)
        self.assertEqual(output[0]["custom_fields"], [20, 21, 22])
        self.assertEqual(output[0]["compression"], "none")

    def test_v2_uncompressed_extended_entry(self):
        output = parse_android_dtbo(dtbo_image(2, synthetic_fdt()), with_metadata=True)
        self.assertEqual(output[0]["table_version"], 2)
        self.assertEqual(output[0]["custom_fields"], list(range(11)))
        self.assertEqual(output[0]["compression"], "none")

    def test_v1_zlib_decompressed_fdt(self):
        output = parse_android_dtbo(dtbo_image(
            1, zlib.compress(synthetic_fdt()), flags=1), with_metadata=True)
        self.assertEqual(output[0]["compression"], "zlib")
        self.assertEqual(output[0]["fdt"], synthetic_fdt())

    def test_v2_gzip_decompressed_fdt(self):
        output = parse_android_dtbo(dtbo_image(
            2, gzip.compress(synthetic_fdt()), flags=2), with_metadata=True)
        self.assertEqual(output[0]["compression"], "gzip")
        self.assertEqual(output[0]["fdt"], synthetic_fdt())

    def test_v2_optional_lz4_frame_decompressed_fdt(self):
        try:
            import lz4.frame
        except ImportError:
            self.skipTest("optional Python lz4.frame not installed")
        compressed = lz4.frame.compress(synthetic_fdt())
        output = parse_android_dtbo(
            dtbo_image(2, compressed, flags=3), with_metadata=True)
        self.assertEqual(output[0]["compression"], "lz4")
        self.assertEqual(output[0]["fdt"], synthetic_fdt())

    def test_reject_wrong_entry_size_for_version(self):
        with self.assertRaisesRegex(ValueError, "entry size"):
            parse_android_dtbo(dtbo_image(
                1, synthetic_fdt(), entry_size_override=64))

    def test_reject_unknown_dtbo_table_version(self):
        image = bytearray(dtbo_image(1, synthetic_fdt()))
        struct.pack_into(">I", image, 28, 4)
        with self.assertRaisesRegex(ValueError, "unsupported Android DT table version"):
            parse_android_dtbo(image)

    def test_reject_undefined_flags(self):
        with self.assertRaisesRegex(ValueError, "unrecognized flags"):
            parse_android_dtbo(dtbo_image(1, synthetic_fdt(), flags=0x100))

    def test_reject_unknown_compression(self):
        with self.assertRaisesRegex(ValueError, "unsupported compression"):
            parse_android_dtbo(dtbo_image(2, synthetic_fdt(), flags=4))

    def test_reject_corrupt_zlib_data(self):
        with self.assertRaisesRegex(ValueError, "corrupt compressed data"):
            parse_android_dtbo(dtbo_image(1, b"notvalidzlib", flags=1))

    def test_reject_gzip_trailing_compressed_bytes(self):
        with self.assertRaisesRegex(ValueError, "trailing compressed data"):
            parse_android_dtbo(dtbo_image(
                2, gzip.compress(synthetic_fdt()) + b"nonzero", flags=2))

    def test_reject_invalid_page_size(self):
        with self.assertRaisesRegex(ValueError, "page size"):
            parse_android_dtbo(dtbo_image(
                0, synthetic_fdt(), page_size=3000))

    def test_reject_metadata_region_overflow(self):
        image = bytearray(dtbo_image(2, synthetic_fdt()))
        struct.pack_into(">I", image, 16, 257)
        with self.assertRaisesRegex(ValueError, "entry count"):
            parse_android_dtbo(image)

    def test_reject_truncated_gzip(self):
        with self.assertRaisesRegex(ValueError, "truncated/trailing compressed data|corrupt"):
            parse_android_dtbo(dtbo_image(
                1, gzip.compress(synthetic_fdt())[:-4], flags=2))


if __name__ == "__main__":
    unittest.main()
