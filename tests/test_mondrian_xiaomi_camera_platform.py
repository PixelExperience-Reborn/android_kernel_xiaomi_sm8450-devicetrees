"""Fail-closed checks for official Xiaomi Cape camera platform source."""
import copy
import json
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import verify_mondrian_xiaomi_camera_platform as gate


class MondrianXiaomiCameraSourceTests(unittest.TestCase):
    def setUp(self):
        self.lock = json.loads(
            (ROOT / "mondrian-camera-platform-source-lock.json").read_text())

    def test_manifest_only_locks_manufacturer_cape_platform(self):
        gate.verify_lock(self.lock)
        self.assertFalse(
            self.lock["policy"]["cape_platform_camera_overlay_compiled"])
        self.assertFalse(
            self.lock["policy"]["sensor_overlays_from_reference_device_compiled"])

    def test_no_unauthorized_manufacturer_or_board_selection(self):
        for group, key, val in (
            ("manufacturer_platform", "commit", "0" * 40),
            ("manufacturer_platform", "tree", "0" * 40),
            ("manufacturer_platform", "revision_branch", "reference-donor"),
            ("policy", "production_camera_dtbo_approved", True),
            ("policy", "sensor_overlays_from_reference_device_compiled", True),
            ("policy", "lineage_source_imported", True),
            ("policy", "target_device_only", "other"),
        ):
            with self.subTest(group=group, key=key):
                candidate = copy.deepcopy(self.lock)
                candidate[group][key] = val
                with self.assertRaisesRegex(ValueError, "unreviewed"):
                    gate.verify_lock(candidate)

    def test_exact_micode_urls_and_gitlink_only(self):
        gate.verify_config((ROOT / ".gitmodules").read_text())
        expected = ("160000 commit " + gate.SOURCE_COMMIT +
                    "\t" + gate.SOURCE_PATH)
        gate.verify_gitlink(expected)
        with self.assertRaisesRegex(ValueError, "Gitlink"):
            gate.verify_gitlink(expected.replace(gate.SOURCE_COMMIT, "0" * 40))
        with self.assertRaisesRegex(ValueError, "path/URL"):
            gate.verify_config((ROOT / ".gitmodules").read_text().replace(
                gate.SOURCE_URL, "https://example.com/camera-donor.git"))

    def test_original_cape_source_controllers(self):
        source = ROOT / gate.SOURCE_PATH
        gate.verify_cape_platform_source(
            (source / "cape-camera.dtsi").read_text(),
            (source / "cape-camera.dts").read_text())
        self.assertEqual(len(gate.PLATFORM_CONTROLLERS), 10)

    def test_missing_cci_and_sensor_include_fail_closed(self):
        source = ROOT / gate.SOURCE_PATH
        cape = (source / "cape-camera.dtsi").read_text()
        target = (source / "cape-camera.dts").read_text()
        with self.assertRaisesRegex(ValueError, "CCI"):
            gate.verify_cape_platform_source(
                cape.replace('compatible = "qcom,cci", "simple-bus";',
                             'compatible = "unreviewed,cci";', 1), target)
        with self.assertRaisesRegex(ValueError, "reference sensor"):
            gate.verify_cape_platform_source(
                cape, target + '\n#include "cape-camera-sensor-mtp.dtsi"\n')

    def test_oem_original_files_and_not_external_rom(self):
        self.assertEqual(self.lock["manufacturer_platform"]["files"],
                         gate.FILE_BLOBS)
        self.assertEqual(self.lock["soc"], "SM8475")
        self.assertFalse(self.lock["policy"]["lineage_source_imported"])
        self.assertFalse(self.lock["policy"]["fm_radio_included"])


if __name__ == "__main__":
    unittest.main()
