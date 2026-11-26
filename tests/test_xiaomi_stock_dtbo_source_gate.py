"""Reject unknown panel sources; validate read-only OEM DTBO structure parsing."""
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_xiaomi_stock_dtbo import (  # noqa: E402
    DT_TABLE_MAGIC, FDT_MAGIC, inspect_dts, parse_android_dtbo,
)


def mock_fdt():
    # Header-only structure for parser unit tests, never hardware evidence.
    return struct.pack(">10I", FDT_MAGIC, 40, 40, 40, 40, 17, 16, 0, 0, 0)


def mock_android_dtbo(*dtbs):
    count = len(dtbs)
    offset = 32 + count * 32
    entries = []
    for i, dtb in enumerate(dtbs):
        entries.append(struct.pack(">8I", len(dtb), offset, 530, i,
                                   0, 0, 0, 0))
        offset += len(dtb)
    header = struct.pack(">8I", DT_TABLE_MAGIC, offset, 32, 32,
                         count, 32, 4096, 0)
    return header + b"".join(entries) + b"".join(dtbs)


class XiaomiStockDtboTests(unittest.TestCase):
    def test_header_only_raw_fdt_is_accepted_as_structural_input(self):
        entries = parse_android_dtbo(mock_fdt())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0][3], mock_fdt())

    def test_parse_android_dt_table_multiple_entries(self):
        data = mock_android_dtbo(mock_fdt(), mock_fdt())
        entries = parse_android_dtbo(data)
        self.assertEqual(len(entries), 2)
        self.assertEqual([r[2] for r in entries], [0, 1])
        self.assertEqual([r[1] for r in entries], [530, 530])

    def test_accept_only_zero_fdt_alignment_padding(self):
        padded = mock_android_dtbo(mock_fdt() + b"\x00" * 4)
        entries = parse_android_dtbo(padded)
        self.assertEqual(entries[0][3], mock_fdt())
        corrupted = mock_android_dtbo(mock_fdt() + b"\x01" * 4)
        with self.assertRaises(ValueError):
            parse_android_dtbo(corrupted)

    def test_reject_unreviewed_android_dt_table_version(self):
        data = bytearray(mock_android_dtbo(mock_fdt()))
        # AOSP now specifies v0, v1 and v2. Version 3 is not specified.
        struct.pack_into(">I", data, 28, 3)
        with self.assertRaisesRegex(ValueError, "unsupported Android DT table version"):
            parse_android_dtbo(data)

    def test_reject_image_too_short(self):
        with self.assertRaises(ValueError):
            parse_android_dtbo(b"\x00" * 20)

    def test_reject_wrong_magic(self):
        with self.assertRaises(ValueError):
            parse_android_dtbo(b"\x11" * 64)

    def test_reject_fdt_size_outside_entry(self):
        data = bytearray(mock_android_dtbo(mock_fdt()))
        struct.pack_into(">I", data, 32 + 32 + 4, 9999)
        with self.assertRaises(ValueError):
            parse_android_dtbo(data)

    def test_reject_entry_outside_image(self):
        data = bytearray(mock_android_dtbo(mock_fdt()))
        struct.pack_into(">I", data, 32 + 4, 0xFFFFFF00)
        with self.assertRaises(ValueError):
            parse_android_dtbo(data)

    def test_reject_table_overflow(self):
        data = bytearray(mock_android_dtbo(mock_fdt()))
        struct.pack_into(">I", data, 16, 257)
        with self.assertRaises(ValueError):
            parse_android_dtbo(data)

    def test_reject_entry_overlapping_metadata(self):
        data = bytearray(mock_android_dtbo(mock_fdt()))
        struct.pack_into(">I", data, 32 + 4, 32)
        with self.assertRaises(ValueError):
            parse_android_dtbo(data)

    def test_panel_strings_are_candidates_not_qualifications(self):
        flags = inspect_dts('qcom,mdss-dsi-panel-name; m11a; mi,local-hbm-enabled;')
        self.assertTrue(flags["mentions_m11a"])
        self.assertFalse(flags["panel_description_present"])
        self.assertFalse(flags["dsc_property_present"])

    def test_oem_m11a_product_gate_stays_closed_without_manufacturer_source(self):
        lock = json.loads((ROOT / "oem-m11a-panel-source-lock.json").read_text())
        self.assertEqual(lock["device"], "mondrian")
        self.assertEqual(lock["soc"], "SM8475")
        self.assertEqual(lock["android_base"], "AOSP 17")
        self.assertEqual(lock["oem_published_dts"]["repository"],
                         "MiCode/kernel_devicetree")
        self.assertEqual(lock["oem_published_dts"]["branch"], "mondrian-s-oss")
        self.assertFalse(lock["oem_published_dts"]["confirmed_panel_source_available"])
        self.assertIsNone(lock["stock_firmware"]["dtbo_sha256"])
        self.assertIsNone(lock["stock_firmware"]["vendor_boot_sha256"])
        self.assertIsNone(lock["stock_firmware"]["vendor_boot_embedded_dtb_count"])
        self.assertFalse(lock["qualification"]["manufacturer_vendor_boot_dtb_reviewed"])
        self.assertFalse(lock["qualification"]["manufacturer_dtbo_and_vendor_boot_crosschecked"])
        self.assertFalse(lock["qualification"]["manufacturer_panel_parameters_verified"])
        self.assertFalse(lock["qualification"]["independent_pe_panel_dts_implemented"])
        self.assertFalse(lock["qualification"]["production_dtbo_img_approved"])
        self.assertFalse(lock["product_selection_allowed"])
        # Reject panel payloads anywhere under qcom/, not only display/.
        # Existing OEM touch firmware names mention m11a and remain valid.
        for panel_dts in (ROOT / "qcom").rglob("*"):
            if not panel_dts.is_file() or panel_dts.suffix not in (".dts", ".dtsi"):
                continue
            text = panel_dts.read_text(errors="replace")
            self.assertNotIn("qcom,mdss-dsi-panel-name", text,
                             f"Unreviewed panel DTS added: {panel_dts}")
            self.assertNotIn("mi,local-hbm-enabled", text,
                             f"Unreviewed Xiaomi LHBM commands added: {panel_dts}")
        # The OEM seven-file board source lock remains immutable.
        board_lock = json.loads((ROOT / "oem-source-lock.json").read_text())
        self.assertEqual(len(board_lock["original_git_blobs"]), 14)


if __name__ == "__main__":
    unittest.main()
