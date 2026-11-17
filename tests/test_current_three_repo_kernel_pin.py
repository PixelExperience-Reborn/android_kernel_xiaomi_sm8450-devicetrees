"""Selected three-repository Kernel revision must be coherent without rewriting history."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
KERNEL = "a146a1df7e458ab899d6084ed3ddb75699ad3b82"
OEM_DT = "34e6cc7d832ed9c655b9d79bc3ffe1d625146b7c"
OLD_EVIDENCE = "2466406b9beac724960b0c88e6e794421d0466e7"


class MondrianCurrentKernelPinTests(unittest.TestCase):
    def test_selected_oem_board_uses_verified_camera_power_kernel(self):
        lock = json.loads((ROOT / "oem-source-lock.json").read_text())
        self.assertEqual(lock["device"], "mondrian")
        self.assertEqual(lock["android_base"], "AOSP 17")
        self.assertEqual(lock["selected_kernel_commit"], KERNEL)
        self.assertEqual(lock["source_commit"], OEM_DT)
        self.assertFalse(lock["qualifications"]["hardware_booted"])

    def test_original_2026_build_is_not_relabelled_as_new_kernel(self):
        lock = json.loads((ROOT / "oem-source-lock.json").read_text())
        self.assertEqual(lock["diagnostic_evidence"]["kernel_commit"], OLD_EVIDENCE)
        self.assertFalse(lock["diagnostic_evidence"]["production_dtbo_img_built"])

    def test_every_active_dtbo_workflow_uses_same_reviewed_kernel(self):
        workflows = (
            "oem-dtbo-compile.yml",
            "oem-coherent-dtbo-compile.yml",
            "mondrian-oem-camera-platform-compile.yml",
        )
        for name in workflows:
            with self.subTest(workflow=name):
                text = (ROOT / ".github/workflows" / name).read_text()
                self.assertIn("ref: " + KERNEL, text)
                self.assertNotIn("ref: " + OLD_EVIDENCE, text)
        camera = (ROOT / "tools/build_mondrian_camera_platform.py").read_text()
        self.assertIn('KERNEL_SHA = "' + KERNEL + '"', camera)

    def test_no_donor_sensor_or_product_camera_dtbo_is_enabled(self):
        lock = json.loads((ROOT / "mondrian-camera-platform-source-lock.json").read_text())
        self.assertFalse(lock["policy"]["production_camera_dtbo_approved"])
        self.assertFalse(lock["policy"]["sensor_overlays_from_reference_device_compiled"])


if __name__ == "__main__":
    unittest.main()
