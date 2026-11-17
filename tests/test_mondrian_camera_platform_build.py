"""Regression guards for a separate manufacturer Cape Camera platform DTBO."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_mondrian_camera_platform import (
    PLATFORM_COMPATIBLES, assert_baseline_preserved,
    compatible, validate_overlay_source, verify_camera_platform_nodes,
)


class MondrianCameraPlatformBuildTests(unittest.TestCase):
    def setUp(self):
        self.overlay = (ROOT /
                        "qcom/mondrian-sm8475-camera-platform-overlay.dts"
                        ).read_text()

    def test_native_overlay_is_only_generic_xiaomi_camera_hardware(self):
        validate_overlay_source(self.overlay)
        self.assertEqual(PLATFORM_COMPATIBLES[b"qcom,cci"], 2)
        self.assertEqual(PLATFORM_COMPATIBLES[b"qcom,csiphy"], 6)

    def test_reference_sensors_and_bootloader_selector_are_blocked(self):
        for injected in (
            '\n#include "cape-camera-sensor-mtp.dtsi"\n',
            '\n/ { model = "Unqualified donor"; };\n',
            '\n/ { qcom,board-id = <8 0>; };\n',
            '\n&soc { sensor { compatible = "qcom,cam-sensor"; }; };\n',
            '\n&soc { flash { flash-source = <0x123>; }; };\n',
        ):
            with self.subTest(injected=injected):
                with self.assertRaises(ValueError):
                    validate_overlay_source(self.overlay + injected)

    def test_preserves_existing_oem_gpio_pmic_and_board_properties(self):
        before = {
            "/": {"model": b"Cape\0", "xiaomi,miboard-id": b"\0\0\0\x0e"},
            "/soc": {"compatible": b"simple-bus\0"},
            "/soc/pmi": {"qcom,led-mask": b"\0\0\0\x09"},
            "/soc/goodix": {"compatible": b"goodix,gt9916S\0"},
            "/soc/wlan": {"compatible": b"qcom,cnss-qca6490\0"},
        }
        after = dict(before)
        after["/soc/new-camera-cci"] = {"compatible": b"qcom,cci\0"}
        self.assertTrue(assert_baseline_preserved(before, after))
        bad = dict(after)
        bad["/soc/pmi"] = {"qcom,led-mask": b"\0\0\0\x01"}
        with self.assertRaisesRegex(ValueError, "rewrote"):
            assert_baseline_preserved(before, bad)

    def test_complete_controller_count_and_absent_sensor_qualification(self):
        before = {"/": {"model": b"Cape\0"}}
        after = dict(before)
        groups = (
            (b"qcom,cci", 2),
            (b"qcom,csiphy", 6),
            (b"qcom,cam-cpas", 1),
            (b"qcom,cam-req-mgr", 1),
        )
        for compat, n in groups:
            for i in range(n):
                after["/soc/" + compat.decode("ascii") + str(i)] = {
                    "compatible": compat + b"\0",
                }
        self.assertEqual(len(verify_camera_platform_nodes(
            before, after)[ "qcom,csiphy"]), 6)
        after["/soc/donor"] = {"compatible": b"qcom,camera-flash\0"}
        with self.assertRaisesRegex(ValueError, "unqualified"):
            verify_camera_platform_nodes(before, after)

    def test_missing_camera_controller_fails_closed(self):
        before = {"/": {"model": b"Cape\0"}}
        with self.assertRaisesRegex(ValueError, "controller count"):
            verify_camera_platform_nodes(before, before)

    def test_malformed_compatible_string_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid FDT"):
            compatible({"compatible": b"qcom,cci"})

    def test_original_provenance_lock_keeps_hardware_unqualified(self):
        lock = json.loads((ROOT /
                           "mondrian-camera-platform-source-lock.json").read_text())
        self.assertFalse(lock["policy"]["production_camera_dtbo_approved"])
        self.assertFalse(lock["policy"][
            "sensor_overlays_from_reference_device_compiled"])
        self.assertEqual(lock["device"], "mondrian")


if __name__ == "__main__":
    unittest.main()
