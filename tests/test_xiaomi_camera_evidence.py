"""Synthetic FDT tests for OEM Camera Flash evidence. No donor DTS copied."""
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_xiaomi_camera_evidence import camera_flash_evidence_from_fdt
from test_xiaomi_panel_evidence import FdtBuilder


def build_camera_fdt(*, unresolved=False, mask=9, bad_mask=False):
    b = FdtBuilder()
    b.begin("")
    b.begin("soc")
    b.begin("pmic-flash")
    b.cells("phandle", 0x12)
    b.string("qcom,default-led-trigger", "flash0_trigger")
    b.end()
    b.begin("pmic-torch")
    b.cells("phandle", 0x13)
    b.end()
    b.begin("pmic-switch")
    b.cells("phandle", 0x14)
    if bad_mask:
        b.prop("qcom,led-mask", b"\x00\x09")
    else:
        b.cells("qcom,led-mask", mask)
    b.end()
    b.begin("camera-flash@1")
    b.string("compatible", "qcom,camera-flash")
    b.cells("cell-index", 1)
    b.string("status", "okay")
    b.cells("flash-source", 0xFFFFFFFF if unresolved else 0x12)
    b.cells("torch-source", 0x13)
    b.cells("switch-source", 0x14)
    b.end()
    b.end()
    if unresolved:
        b.begin("__fixups__")
        b.string("pm8350c_flash0",
                 "/soc/camera-flash@1:flash-source:0")
        b.end()
    b.end()
    return b.build()


class XiaomiCameraFdtTests(unittest.TestCase):
    def test_resolves_real_local_phandles_without_guessing_a_mask(self):
        report = camera_flash_evidence_from_fdt(build_camera_fdt())
        self.assertEqual(report["camera_flash_node_count"], 1)
        candidate = report["camera_flash_candidates"][0]
        self.assertTrue(candidate["all_sources_resolved_within_this_fdt"])
        self.assertEqual(candidate["source_references"]["flash-source"][0][
            "local_target_node"], "/soc/pmic-flash")
        self.assertEqual(report["led_mask_candidates"][0]["mask_as_published"], 9)
        self.assertFalse(report["camera_dtbo_safe_for_product"])
        self.assertFalse(report["physical_flash_hardware_qualified"])

    def test_external_fixup_is_unresolved_even_if_symbol_names_pmic(self):
        report = camera_flash_evidence_from_fdt(
            build_camera_fdt(unresolved=True))
        source = report["camera_flash_candidates"][0][
            "source_references"]["flash-source"][0]
        self.assertEqual(source["resolution"], "external_fixup_unresolved")
        self.assertEqual(source["external_fixup_symbols"], ["pm8350c_flash0"])
        self.assertIsNone(source["local_target_node"])
        self.assertEqual(report["unresolved_source_reference_count"], 1)
        self.assertFalse(report["camera_dtbo_safe_for_product"])

    def test_no_literal_lineage_mask_or_xiaomi_channel_approval(self):
        for mask in (1, 9, 15):
            with self.subTest(mask=mask):
                report = camera_flash_evidence_from_fdt(
                    build_camera_fdt(mask=mask))
                self.assertEqual(report["led_mask_candidates"][0][
                    "mask_as_published"], mask)
                self.assertFalse(report["led_mask_candidates"][0][
                    "mask_is_mondrian_camera_channel_verified"])
                self.assertFalse(report["pm8350c_flash_channel_or_gpio356_inferred"])

    def test_rejects_non_u32_led_mask(self):
        with self.assertRaisesRegex(ValueError, "qcom,led-mask"):
            camera_flash_evidence_from_fdt(build_camera_fdt(bad_mask=True))

    def test_absent_camera_is_not_false_positive(self):
        b = FdtBuilder()
        b.begin("")
        b.begin("soc")
        b.begin("unrelated-flash")
        b.string("compatible", "mycorp,unrelated-flash")
        b.end()
        b.end()
        b.end()
        report = camera_flash_evidence_from_fdt(b.build())
        self.assertEqual(report["camera_flash_node_count"], 0)
        self.assertFalse(report["camera_dtbo_safe_for_product"])

    def test_root_devicetree_and_product_remain_unchanged(self):
        lock = json.loads((ROOT / "oem-source-lock.json").read_text())
        self.assertEqual(lock["source_repository"], "MiCode/kernel_devicetree")
        self.assertEqual(lock["source_commit"],
                         "34e6cc7d832ed9c655b9d79bc3ffe1d625146b7c")
        self.assertFalse(lock["qualifications"]["display_camera_overlays_compiled"])
        self.assertFalse((ROOT / "qcom/camera").exists())


if __name__ == "__main__":
    unittest.main()
