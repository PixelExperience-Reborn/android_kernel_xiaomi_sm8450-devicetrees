"""Check OEM QCA6490 hardware properties without changing Xiaomi DTS."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class MondrianQca6490Contract(unittest.TestCase):
    def test_qca6490_comes_from_selected_xiaomi_cape_tree(self):
        src = (ROOT / "upstream/xiaomi-dts/qcom/cape.dtsi").read_text()
        self.assertEqual(src.count('compatible = "qcom,cnss-qca6490";'), 1)
        for v in ('wlan: qcom,cnss-qca6490@b0000000 {',
                  'wlan-en-gpio = <&tlmm 80 0>;',
                  'qcom,bt-en-gpio = <&tlmm 81 0>;',
                  'qcom,sw-ctrl-gpio = <&tlmm 82 0>;',
                  'vdd-wlan-aon-supply',
                  'vdd-wlan-dig-supply',
                  'vdd-wlan-io-supply',
                  'vdd-wlan-rfa1-supply',
                  'vdd-wlan-rfa2-supply',
                  'wlan-ant-switch-supply',
                  'qcom,wlan-rc-num = <0>;',
                  'qcom,wlan-ramdump-dynamic = <0x420000>;'):
            self.assertIn(v, src)

    def test_goodix_udfps_oem_gpio_and_regulator_matches_our_kernel(self):
        board = (ROOT / "qcom/mondrian-sm8475.dtsi").read_text()
        self.assertIn('compatible = "goodix,fingerprint";', board)
        self.assertIn('goodix,gpio-reset = <&tlmm 41 0x0>;', board)
        self.assertIn('goodix,gpio-irq = <&tlmm 40 0x0>;', board)
        self.assertIn('l1c_vdd-supply = <&L9C>;', board)
        # The actual OEM kernel at 2466406 uses the Goodix G3S driver,
        # which reads these exact DT properties (not a foreign HAL).
        self.assertIn('regulator-min-microvolt = <3200000>;', board)

    def test_diagnostic_contract_is_not_claimed_to_be_hw_validation(self):
        lock = json.loads((ROOT / "oem-source-lock.json").read_text())
        evidence = lock["diagnostic_evidence"]
        self.assertTrue(evidence["qca6490_oem_cnss_and_regulator_contract_verified"])
        self.assertFalse(evidence["qca6490_hardware_rf_and_firmware_verified"])
        self.assertTrue(evidence["goodix_udfps_oem_bindings_verified"])
        self.assertFalse(evidence["goodix_udfps_device_runtime_verified"])
        self.assertFalse(evidence["production_dtbo_img_built"])


if __name__ == "__main__":
    unittest.main()
