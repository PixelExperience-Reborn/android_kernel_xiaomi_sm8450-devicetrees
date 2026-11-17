"""Source-only checks for OEM mondrian Camera board vs donor controller contracts."""
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_mondrian_camera_source_contract import (
    validate_board, validate_donor_controller_source, git_blob_sha,
)


BOARD = '#include "mondrian-sm8475.dtsi"\n#include "mondrian-wl2866d.dtsi"\n'
REGULATOR = """&qupv3_se5_i2c {
    wl2866d@28 {
        compatible = "xiaomi,wl2866d";
        reg = <0x28>;
        vin1-supply = <&S12B>;
        vin2-supply = <&BOB>;
        en-gpio = <&tlmm 44 0>;
    };
};
"""
CAPE = "\n".join([
    "cam_cci0:", "cam_cci1:",
    *(f"cam_csiphy{i}:" for i in range(6)),
    'compatible = "qcom,cam-cpas"',
    'compatible = "qcom,cam-req-mgr"',
])
OVERLAY = ("/dts-v1/;\n/plugin/;\n" +
           "\n".join(f"#include {h}" for h in (
               "<dt-bindings/clock/qcom,gcc-waipio.h>",
               "<dt-bindings/clock/qcom,camcc-waipio.h>",
               "<dt-bindings/interconnect/qcom,waipio.h>",
               "<dt-bindings/interrupt-controller/arm-gic.h>",
               "<dt-bindings/regulator/qcom,rpmh-regulator-levels.h>",
               '"cape-camera.dtsi"')))


class MondrianCameraOemSourceContractTests(unittest.TestCase):
    def test_board_source_contract(self):
        self.assertEqual(len(validate_board(REGULATOR, BOARD)), 9)

    def test_wrong_i2c_address_rejected(self):
        with self.assertRaises(ValueError):
            validate_board(REGULATOR.replace("<0x28>", "<0x29>"), BOARD)

    def test_wrong_gpio_rejected(self):
        with self.assertRaises(ValueError):
            validate_board(REGULATOR.replace("tlmm 44", "tlmm 45"), BOARD)

    def test_wrong_rail_rejected(self):
        with self.assertRaises(ValueError):
            validate_board(REGULATOR.replace("<&BOB>", "<&OTHER>"), BOARD)

    def test_missing_board_include_rejected(self):
        with self.assertRaises(ValueError):
            validate_board(REGULATOR, BOARD.replace("mondrian-wl2866d.dtsi", "foreign.dtsi"))

    def test_source_controllers_present(self):
        self.assertEqual(
            validate_donor_controller_source(CAPE, OVERLAY)["csiphy_count"], 6)

    def test_missing_controller_rejected(self):
        with self.assertRaises(ValueError):
            validate_donor_controller_source(CAPE.replace("cam_csiphy5:", ""), OVERLAY)

    def test_donor_sensor_include_rejected(self):
        with self.assertRaises(ValueError):
            validate_donor_controller_source(
                CAPE, OVERLAY + '\n#include "flame-camera-sensor-mtp.dtsi"\n')

    def test_git_blob_identity_does_not_equal_raw_sha1(self):
        import hashlib
        self.assertNotEqual(git_blob_sha(b"OEM"), hashlib.sha1(b"OEM").hexdigest())


if __name__ == "__main__":
    unittest.main()
