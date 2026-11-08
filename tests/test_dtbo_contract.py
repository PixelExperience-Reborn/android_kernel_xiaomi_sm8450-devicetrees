import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DtboContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads((ROOT / "dtbo-bsp-candidates.json").read_text())

    def test_mondrian_scope_and_reference_commit(self):
        d = self.cfg
        self.assertEqual(d["schema_version"], 1)
        self.assertEqual(d["device"], "mondrian")
        self.assertEqual(d["soc"], "SM8475")
        self.assertEqual(d["android_base"], "AOSP 17")
        self.assertEqual(d["build_status"], "not_buildable")
        s = d["reference_source"]
        self.assertEqual(s["status"], "read_only_not_selected")
        self.assertNotEqual(s["commit_sha"], s["tree_sha"])

    def test_real_platform_layers_are_separate(self):
        r = self.cfg["expected_reference"]
        self.assertEqual(r["soc_dtbs"], ["cape.dtb", "cape-v2.dtb", "capep.dtb"])
        self.assertEqual(r["mondrian_board_dtbo"], "mondrian-sm8475-pm8008-overlay.dtbo")
        self.assertEqual(r["display_dtbo"], "mondrian-sde-display-mtp-overlay.dtbo")
        self.assertEqual(r["camera_dtbo"], "mondrian-sm8475-camera-sensor.dtbo")
        self.assertIn("m11a", r["panel_include"])

    def test_touch_and_fingerprint_not_interchangeable(self):
        r = self.cfg["expected_reference"]
        self.assertEqual(r["touch_spi_compatible"], "goodix,gt9916S")
        self.assertEqual(r["manufacturer_spi_compatible"], "goodix,brl-d")
        self.assertNotEqual(r["touch_spi_compatible"], r["manufacturer_spi_compatible"])
        self.assertEqual(r["fingerprint_compatible"], "goodix,fingerprint")
        self.assertTrue(r["touch_and_fingerprint_are_independent"])

    def test_lf_trial_dt_source_is_pinned_to_same_kernel(self):
        t = self.cfg["trial_lf_source"]
        self.assertEqual(t["repository"], "LF52406/android_kernel_xiaomi_sm8450-devicetrees")
        self.assertEqual(t["commit_sha"], "99f1330d8dce0c80de5a19f425d0a118b2eb7fe3")
        self.assertEqual(t["root_tree_sha"], "fcbd44856a59364a8af9ebc72546ea8ecab0f77b")
        self.assertEqual(t["expected_kernel_commit"], "283772ceb84491fd446e340fd211d45fb9dd9a36")
        self.assertEqual(t["board_blob_sha"], "59cb230a704b67b3f8800682937bbec2a9e09f9c")
        self.assertEqual(t["board_overlay_base_dtbs"], ["cape.dtb", "cape-v2.dtb", "capep.dtb"])
        self.assertEqual(t["status"], "trial_source_only_not_copied_or_compiled")
        for key in ("physical_hardware_board_revision_verified", "device_tree_compiled",
                    "overlays_applied_to_all_compatible_bases"):
            self.assertFalse(t[key])

    def test_no_unverified_device_tree_is_accepted(self):
        q = self.cfg["required_qualification"]
        for key in ("kernel_commit", "module_commit", "kernel_config_hash"):
            self.assertIsNone(q[key])
        self.assertFalse(any(x for x in q.values() if x is not None))
        self.assertIn("FM radio", self.cfg["exclusions"])

    def test_file_pins_are_immutable_blob_ids(self):
        arr = self.cfg["verified_reference_files"]
        self.assertEqual(len(arr), 5)
        self.assertEqual(len({x["path"] for x in arr}), 5)
        for item in arr:
            self.assertRegex(item["blob_sha"], r"^[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
