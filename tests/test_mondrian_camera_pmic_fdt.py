"""Synthetic FDT regression tests for manufacturer Camera PMIC source wiring."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from verify_mondrian_camera_pmic_fdt import verify_mondrian_camera_pmic_fdt
from test_xiaomi_panel_evidence import FdtBuilder


def sample_pmic(*, bad_label="", bad_trigger=False, mask=9, status="ok",
                active_consumer=False):
    b = FdtBuilder()
    b.begin("")
    b.begin("soc")
    b.begin("spmi")
    b.begin("qcom,flash_led@ee00")
    b.string("compatible", "qcom,pm8350c-flash-led")
    b.string("status", status)
    rows = {
        "pm8350c_flash0": ("qcom,flash_0", "flash0_trigger", None),
        "pm8350c_torch0": ("qcom,torch_0", "torch0_trigger", None),
        "pm8350c_switch0": ("qcom,led_switch_0", "switch0_trigger", mask),
        "pm8350c_switch1": ("qcom,led_switch_1", "switch1_trigger", 6),
        "pm8350c_switch2": ("qcom,led_switch_2", "switch2_trigger", 15),
    }
    for label, (name, trigger, value) in rows.items():
        if label == bad_label:
            continue
        b.begin(name)
        b.string("qcom,default-led-trigger",
                 "invalid-gpio-trigger" if bad_trigger and
                 label == "pm8350c_flash0" else trigger)
        if value is not None:
            b.cells("qcom,led-mask", value)
            b.prop("qcom,symmetry-en", b"")
        b.end()
    b.end()
    b.end()
    b.end()
    if active_consumer:
        b.begin("unqualified-camera")
        b.string("compatible", "qcom,camera-flash")
        b.string("status", "okay")
        b.end()
    b.begin("__symbols__")
    for label, (name, _, _) in rows.items():
        if label != bad_label:
            b.string(label, "/soc/spmi/qcom,flash_led@ee00/" + name)
    b.end()
    b.end()
    return b.build()


class PmicCameraOemSourceTests(unittest.TestCase):
    def test_compiled_pmic_label_targets_and_no_hardware_claim(self):
        data = verify_mondrian_camera_pmic_fdt(sample_pmic())
        self.assertTrue(data["oem_pmic_source_links_resolved_in_compiled_dtb"])
        self.assertEqual(len(data["flash_torch_and_switch_phandle_targets"]), 5)
        self.assertEqual(data["xiaomi_common_switch_masks_as_published"],
                         {"pm8350c_switch0": 9, "pm8350c_switch1": 6,
                          "pm8350c_switch2": 15})
        self.assertFalse(data["mondrian_physical_flash_channel_mapping_verified"])
        self.assertFalse(data["production_camera_flash_approved"])

    def test_all_five_missing_xiaomi_resource_labels_block(self):
        for label in ("pm8350c_flash0", "pm8350c_torch0",
                      "pm8350c_switch0", "pm8350c_switch1",
                      "pm8350c_switch2"):
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, "missing Xiaomi"):
                    verify_mondrian_camera_pmic_fdt(
                        sample_pmic(bad_label=label))

    def test_wrong_trigger_rejected(self):
        with self.assertRaisesRegex(ValueError, "trigger mismatch"):
            verify_mondrian_camera_pmic_fdt(sample_pmic(bad_trigger=True))

    def test_source_mask_changes_must_be_reviewed(self):
        for mask in (0, 1, 6, 15, 16):
            with self.subTest(mask=mask):
                with self.assertRaisesRegex(ValueError, "LED-mask"):
                    verify_mondrian_camera_pmic_fdt(sample_pmic(mask=mask))

    def test_disabled_pmic_rejected(self):
        with self.assertRaisesRegex(ValueError, "not enabled"):
            verify_mondrian_camera_pmic_fdt(sample_pmic(status="disabled"))

    def test_unqualified_camera_consumer_rejected(self):
        with self.assertRaisesRegex(ValueError, "unqualified active"):
            verify_mondrian_camera_pmic_fdt(sample_pmic(active_consumer=True))


if __name__ == "__main__":
    unittest.main()
