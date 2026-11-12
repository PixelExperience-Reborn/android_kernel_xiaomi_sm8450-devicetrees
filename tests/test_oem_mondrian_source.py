"""Validate the narrow OEM source import and the one explicit SPI adaptation."""
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def blob_sha(content):
    return hashlib.sha1(b"blob " + str(len(content)).encode() + bytes([0]) + content).hexdigest()


class MondrianOemDtsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = json.loads((ROOT / "oem-source-lock.json").read_text())

    def test_only_mondrian_source_baseline(self):
        d = self.lock
        self.assertEqual(d["device"], "mondrian")
        self.assertEqual(d["soc"], "SM8475")
        self.assertEqual(d["android_base"], "AOSP 17")
        self.assertEqual(d["source_repository"], "MiCode/kernel_devicetree")
        self.assertEqual(len(d["original_git_blobs"]), 7)
        self.assertEqual(len(d["adaptations"]), 3)

    def test_exact_oem_blobs_with_only_three_declared_adaptations(self):
        for path, expected in self.lock["original_git_blobs"].items():
            raw = (ROOT / path).read_bytes()
            for adaptation in self.lock["adaptations"]:
                if path != adaptation["path"]:
                    continue
                a = adaptation["pe_binding"].encode()
                b = adaptation["oem_binding"].encode()
                self.assertEqual(raw.count(a), 1, path)
                self.assertEqual(raw.count(b), 0, path)
                raw = raw.replace(a, b)
            self.assertEqual(blob_sha(raw), expected, path)

    def test_mondrian_board_and_touch_contract(self):
        root = (ROOT / "qcom/mondrian-sm8475-pm8008-overlay.dts").read_text()
        board = (ROOT / "qcom/mondrian-sm8475.dtsi").read_text()
        self.assertIn('xiaomi,miboard-id = <0xE 0>;', root)
        self.assertIn('compatible = "goodix,gt9916S";', board)
        self.assertIn('goodix,firmware-name = "goodix_firmware_m11a.bin";', board)
        self.assertIn('goodix,config-name = "goodix_cfg_group_m11a.bin";', board)
        self.assertIn('<&tlmm 21', board)
        self.assertIn('<&tlmm 20', board)

    def test_compiled_board_overlay_is_only_diagnostic(self):
        self.assertEqual(self.lock["status"],
                         "oem_mondrian_board_dtb_diagnostic_compiled_not_ship_ready")
        gates = self.lock["qualifications"]
        self.assertTrue(gates["dtbo_compiled"])
        self.assertTrue(gates["overlays_applied"])
        self.assertFalse(gates["display_camera_overlays_compiled"])
        self.assertFalse(gates["firmware_resolved"])
        self.assertFalse(gates["hardware_board_revision_verified"])
        self.assertFalse(gates["hardware_booted"])
        evidence = self.lock["diagnostic_evidence"]
        self.assertEqual(evidence["checked_bases"], ["cape", "cape-v2", "capep"])
        self.assertTrue(evidence["fdt_overlay_applied_to_each"])
        self.assertFalse(evidence["production_dtbo_img_built"])
        self.assertEqual(evidence["kernel_commit"],
                         self.lock["selected_kernel_commit"])
        self.assertGreaterEqual(len(self.lock["unresolved"]), 5)


if __name__ == "__main__":
    unittest.main()
