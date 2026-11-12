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

    def test_diagnostic_contract_is_not_claimed_to_be_hw_validation(self):
        lock = json.loads((ROOT / "oem-source-lock.json").read_text())
        evidence = lock["diagnostic_evidence"]
        self.assertTrue(evidence["qca6490_oem_cnss_and_regulator_contract_verified"])
        self.assertFalse(evidence["qca6490_hardware_rf_and_firmware_verified"])
        self.assertFalse(evidence["production_dtbo_img_built"])


if __name__ == "__main__":
    unittest.main()
