"""Synthetic AOSP vendor_boot v3/v4 tests; no Xiaomi firmware copied into CI."""
import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_xiaomi_vendor_boot import (  # noqa: E402
    audit_vendor_boot_data, parse_vendor_boot,
)
from test_xiaomi_camera_evidence import build_camera_fdt  # noqa: E402


def fdt_fixture():
    """Minimal *valid* FDT v17, no hardware or panel-specific properties."""
    # header + zero-terminated reservation map + root begin/end + FDT_END
    structure = struct.pack(">4I", 1, 0, 2, 9)
    size = 40 + 16 + len(structure)
    header = struct.pack(">10I", 0xD00DFEED, size, 56, size, 40,
                         17, 16, 0, 0, len(structure))
    return header + b"\x00" * 16 + structure


def vendor_boot_fixture(version=4, *, ramdisk=b"", dtbs=(), tail=b"",
                        page=4096, table=b"", bootconfig=b""):
    """Construct correct AOSP v3/v4 header with page-aligned sections."""
    hsize = 2112 if version == 3 else 2128
    header = bytearray(page)
    header[:8] = b"VNDRBOOT"
    struct.pack_into("<I", header, 8, version)
    struct.pack_into("<I", header, 12, page)
    struct.pack_into("<I", header, 24, len(ramdisk))
    struct.pack_into("<I", header, 2096, hsize)
    dtb_payload = b"".join(dtbs) + tail
    struct.pack_into("<I", header, 2100, len(dtb_payload))
    if version == 4:
        struct.pack_into("<I", header, 2112, len(table))
        struct.pack_into("<I", header, 2116, 0)
        struct.pack_into("<I", header, 2120, 0)
        struct.pack_into("<I", header, 2124, len(bootconfig))

    def padded(value):
        return value + b"\x00" * (-len(value) % page)

    data = bytes(header) + padded(ramdisk) + padded(dtb_payload)
    if version == 4:
        data += padded(table) + padded(bootconfig)
    return data


class XiaomiVendorBootTests(unittest.TestCase):
    def test_extract_single_dtb_aosp_v3(self):
        payload = vendor_boot_fixture(3, ramdisk=b"synthetic", dtbs=[fdt_fixture()])
        header, parts = parse_vendor_boot(payload)
        self.assertEqual(header["header_version"], 3)
        self.assertEqual(header["vendor_ramdisk_size"], 9)
        self.assertEqual(header["dtb_section_offset"], 8192)
        self.assertEqual(parts, [fdt_fixture()])

    def test_extract_concatenated_fdt_aosp_v4(self):
        payload = vendor_boot_fixture(4, dtbs=[fdt_fixture(), fdt_fixture()])
        header, parts = parse_vendor_boot(payload)
        self.assertEqual(header["header_version"], 4)
        self.assertEqual(len(parts), 2)
        self.assertEqual(header["dtb_size"], 2 * len(fdt_fixture()))

    def test_extract_with_zero_inter_dtb_padding(self):
        payload = vendor_boot_fixture(
            4, dtbs=[fdt_fixture() + b"\x00" * 8, fdt_fixture()])
        _, parts = parse_vendor_boot(payload)
        self.assertEqual(len(parts), 2)

    def test_empty_dtb_section_reports_no_panel(self):
        header, parts = parse_vendor_boot(vendor_boot_fixture(4))
        self.assertEqual(header["dtb_size"], 0)
        self.assertEqual(parts, [])

    def test_reject_invalid_magic(self):
        payload = bytearray(vendor_boot_fixture())
        payload[:8] = b"BADMAGIC"
        with self.assertRaisesRegex(ValueError, "magic"):
            parse_vendor_boot(payload)

    def test_reject_wrong_header_version(self):
        payload = bytearray(vendor_boot_fixture())
        struct.pack_into("<I", payload, 8, 2)
        with self.assertRaisesRegex(ValueError, "versions"):
            parse_vendor_boot(payload)

    def test_reject_wrong_header_size(self):
        payload = bytearray(vendor_boot_fixture())
        struct.pack_into("<I", payload, 2096, 100)
        with self.assertRaisesRegex(ValueError, "header size"):
            parse_vendor_boot(payload)

    def test_reject_bad_page_size(self):
        payload = bytearray(vendor_boot_fixture())
        struct.pack_into("<I", payload, 12, 3)
        with self.assertRaisesRegex(ValueError, "page size"):
            parse_vendor_boot(payload)

    def test_reject_truncated_dtb(self):
        payload = bytearray(vendor_boot_fixture(dtbs=[fdt_fixture()]))
        struct.pack_into("<I", payload, 2100, len(payload))
        with self.assertRaisesRegex(ValueError, "outside image bounds"):
            parse_vendor_boot(payload)

    def test_reject_non_fdt_in_section(self):
        payload = vendor_boot_fixture(dtbs=[fdt_fixture()], tail=b"BADC")
        with self.assertRaisesRegex(ValueError, "invalid FDT"):
            parse_vendor_boot(payload)

    def test_reject_invalid_v4_table_bounds(self):
        payload = bytearray(vendor_boot_fixture(4, dtbs=[fdt_fixture()]))
        struct.pack_into("<I", payload, 2112, 0xFFFFFFFF)
        with self.assertRaisesRegex(ValueError, "table / bootconfig"):
            parse_vendor_boot(payload)

    def test_reject_invalid_v4_entry_metadata(self):
        payload = bytearray(vendor_boot_fixture(4, dtbs=[fdt_fixture()]))
        struct.pack_into("<I", payload, 2116, 2)
        struct.pack_into("<I", payload, 2120, 128)
        with self.assertRaisesRegex(ValueError, "table metadata"):
            parse_vendor_boot(payload)

    def test_both_header_versions_report_camera_and_pmic_links(self):
        # The embedded FDT is synthetic and never validates physical hardware.
        for version in (3, 4):
            with self.subTest(version=version):
                payload = vendor_boot_fixture(
                    version, dtbs=[build_camera_fdt(mask=9)])
                with patch("audit_xiaomi_vendor_boot.shutil.which",
                           return_value="dtc"):
                    with patch("audit_xiaomi_vendor_boot.subprocess.run") as run:
                        run.return_value.stdout = b"synthetic flash DTB;"
                        report = audit_vendor_boot_data(payload)
                entry = report["embedded_dtbs"][0]
                flash = entry["manufacturer_camera_flash_structure"]
                self.assertEqual(flash["camera_flash_node_count"], 1)
                node = flash["camera_flash_candidates"][0]
                self.assertTrue(node["all_sources_resolved_within_this_fdt"])
                self.assertEqual(
                    node["source_references"]["switch-source"][0][
                        "local_target_node"], "/soc/pmic-switch")
                self.assertEqual(
                    flash["led_mask_candidates"][0]["mask_as_published"], 9)
                self.assertFalse(
                    flash["led_mask_candidates"][0][
                        "mask_is_mondrian_camera_channel_verified"])
                self.assertFalse(flash["camera_dtbo_safe_for_product"])
                self.assertFalse(flash["physical_flash_hardware_qualified"])
                self.assertFalse(
                    report["manufacturer_provenance_independently_verified"])

    def test_vendor_boot_external_fixup_does_not_qualify_pmic_channel(self):
        payload = vendor_boot_fixture(
            4, dtbs=[build_camera_fdt(unresolved=True)])
        with patch("audit_xiaomi_vendor_boot.shutil.which",
                   return_value="dtc"):
            with patch("audit_xiaomi_vendor_boot.subprocess.run") as run:
                run.return_value.stdout = b"synthetic camera overlay;"
                evidence = audit_vendor_boot_data(payload)
        flash = evidence["embedded_dtbs"][0][
            "manufacturer_camera_flash_structure"]
        unresolved = flash["camera_flash_candidates"][0][
            "source_references"]["flash-source"][0]
        self.assertEqual(
            unresolved["resolution"], "external_fixup_unresolved")
        self.assertIsNone(unresolved["local_target_node"])
        self.assertEqual(flash["unresolved_source_reference_count"], 1)
        self.assertFalse(flash["camera_dtbo_safe_for_product"])

    def test_vendor_boot_empty_camera_is_not_invented(self):
        payload = vendor_boot_fixture(3, dtbs=[fdt_fixture()])
        with patch("audit_xiaomi_vendor_boot.shutil.which",
                   return_value="dtc"):
            with patch("audit_xiaomi_vendor_boot.subprocess.run") as run:
                run.return_value.stdout = b"synthetic no camera;"
                entry = audit_vendor_boot_data(payload)["embedded_dtbs"][0]
        self.assertEqual(entry["manufacturer_camera_flash_structure"][
            "camera_flash_node_count"], 0)
        self.assertFalse(entry["manufacturer_camera_flash_structure"][
            "camera_dtbo_safe_for_product"])

    def test_malformed_camera_fdt_fails_closed_during_vendor_boot_audit(self):
        payload = vendor_boot_fixture(
            4, dtbs=[build_camera_fdt(bad_mask=True)])
        with patch("audit_xiaomi_vendor_boot.shutil.which",
                   return_value="dtc"):
            with patch("audit_xiaomi_vendor_boot.subprocess.run") as run:
                run.return_value.stdout = b"synthetic malformed LED mask;"
                with self.assertRaisesRegex(ValueError, "qcom,led-mask"):
                    audit_vendor_boot_data(payload)

    def test_audit_never_certifies_panel_from_a_matching_string(self):
        payload = vendor_boot_fixture(4, dtbs=[fdt_fixture()])
        with patch("audit_xiaomi_vendor_boot.shutil.which", return_value="dtc"):
            with patch("audit_xiaomi_vendor_boot.subprocess.run") as runner:
                runner.return_value.stdout = b'm11a; mi,local-hbm-enabled;\n'
                result = audit_vendor_boot_data(payload)
        self.assertEqual(result["embedded_dtb_count"], 1)
        self.assertTrue(result["embedded_dtbs"][0]["candidate_signals"]["mentions_m11a"])
        self.assertFalse(result["embedded_dtbs"][0]["candidate_signals"]["panel_description_present"])
        self.assertFalse(result["manufacturer_provenance_independently_verified"])
        self.assertFalse(result["m11a_panel_ready"])
        self.assertEqual(result["status"], "DIAGNOSTIC_ONLY_NOT_FOR_FLASHING")


if __name__ == "__main__":
    unittest.main()
