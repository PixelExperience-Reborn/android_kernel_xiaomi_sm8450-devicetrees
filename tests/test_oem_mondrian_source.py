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
        self.assertEqual(len(d["adaptations"]), 1)

    def test_exact_oem_blobs_with_one_justified_adaptation(self):
        adaptation = self.lock["adaptations"][0]
        for path, expected in self.lock["original_git_blobs"].items():
            raw = (ROOT / path).read_bytes()
            if path == adaptation["path"]:
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
        self.assertIn('goodix,firmware-name = "goodix_firmware_m11a";', board)
        self.assertIn('goodix,config-name = "goodix_cfg_group_m11a";', board)
        self.assertIn('<&tlmm 21', board)
        self.assertIn('<&tlmm 20', board)

    def test_never_fake_dtbo_completion(self):
        self.assertEqual(self.lock["status"], "oem_board_sources_staged_dtbo_not_buildable")
        self.assertGreaterEqual(len(self.lock["unresolved"]), 5)
        self.assertFalse(any(self.lock["qualifications"].values()))


if __name__ == "__main__":
    unittest.main()
