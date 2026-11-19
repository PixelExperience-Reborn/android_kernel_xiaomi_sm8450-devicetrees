"""Regression guards for a separate manufacturer Cape Camera platform DTBO."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_mondrian_camera_platform import (
    PLATFORM_COMPATIBLES, MONDRIAN_M11A_PHY_IDS, M11A_COMPATIBLE,
    BASE_PHY_COMPATIBLE, assert_baseline_preserved,
    compatible, validate_overlay_source, verify_camera_platform_nodes,
)


class MondrianCameraPlatformBuildTests(unittest.TestCase):
    def setUp(self):
        self.overlay = (ROOT /
                        "qcom/mondrian-sm8475-camera-platform-overlay.dts"
                        ).read_text()

    def test_native_overlay_selects_only_mondrian_m11a_phy2_and_phy4(self):
        validate_overlay_source(self.overlay)
        self.assertEqual(PLATFORM_COMPATIBLES[b"qcom,cci"], 2)
        self.assertEqual(PLATFORM_COMPATIBLES[b"qcom,csiphy"], 6)
        self.assertEqual(MONDRIAN_M11A_PHY_IDS, (2, 4))
        self.assertEqual(self.overlay.count("xiaomi-m11a"), 2)

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
                props = {"compatible": compat + b"\0"}
                if compat == b"qcom,csiphy":
                    version = (M11A_COMPATIBLE if i in MONDRIAN_M11A_PHY_IDS
                               else BASE_PHY_COMPATIBLE)
                    props = {
                        "compatible": version + b"\0qcom,csiphy\0",
                        "cell-index": i.to_bytes(4, "big"),
                    }
                after["/soc/" + compat.decode("ascii") + str(i)] = props
        self.assertEqual(
            len(verify_camera_platform_nodes(before, after)["qcom,csiphy"]), 6)
        phy1 = after["/soc/qcom,csiphy1"]
        after["/soc/qcom,csiphy1"] = {
            **phy1,
            "compatible": M11A_COMPATIBLE + b"\0qcom,csiphy\0",
        }
        with self.assertRaisesRegex(ValueError, "incorrect mondrian CSI PHY"):
            verify_camera_platform_nodes(before, after)
        after["/soc/qcom,csiphy1"] = phy1
        after["/soc/donor"] = {"compatible": b"qcom,camera-flash\0"}
        with self.assertRaisesRegex(ValueError, "unqualified"):
            verify_camera_platform_nodes(before, after)

    def test_m11a_source_rejects_wrong_phy_and_extra_power(self):
        for injected in (
            '\n&cam_csiphy3 { compatible = "qcom,csiphy-v2.1.3-xiaomi-m11a", "qcom,csiphy"; };',
            '\n&cam_csiphy2 { compatible = "qcom,csiphy-v2.1.3-xiaomi-m11a", "qcom,csiphy"; };',
            '\n&pm8350c_switch0 { qcom,led-mask = <1>; };',
        ):
            with self.subTest(injected=injected):
                with self.assertRaises(ValueError):
                    validate_overlay_source(self.overlay + injected)

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
