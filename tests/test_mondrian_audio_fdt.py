"""Synthetic FDT regression checks for the original Xiaomi mondrian speaker board."""
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from verify_mondrian_audio_fdt import verify_mondrian_audio_fdt, MI2S2
from test_xiaomi_panel_evidence import FdtBuilder


def sample_audio(*, wrong_addr=False, wrong_channel=False, wrong_irq=False,
                 wrong_bus=False, missing_amp=False, wrong_mi2s=False,
                 bad_phandle=False, extra_amp=False):
    b = FdtBuilder()
    b.begin("")
    b.begin("soc")
    b.begin("tlmm@1000")
    b.cells("phandle", 7)
    for function, pin in MI2S2.items():
        b.begin(function)
        b.string("function", function)
        b.string("pins", "gpio120" if wrong_mi2s and function == "mi2s2_ws"
                 else pin)
        b.end()
    b.end()

    b.begin("i2c@1200")
    b.string("status", "okay")
    for address, channel, irq, reset, switch in (
            (0x34, 0, 88, 1, 52), (0x35, 1, 63, 3, None)):
        if missing_amp and address == 0x35:
            continue
        b.begin("aw882xx_smartpa@" + format(address, "x"))
        b.string("compatible", "awinic,aw882xx_smartpa")
        b.string("status", "ok")
        b.cells("reg", address + (1 if wrong_addr and address == 0x34 else 0))
        b.cells("sound-channel", 2 if wrong_channel and address == 0x35 else channel)
        b.cells("irq-gpio", 9 if bad_phandle and address == 0x34 else 7,
                86 if wrong_irq and address == 0x34 else irq, 0x2008)
        b.cells("reset-gpio", 7, reset, 0)
        if switch is not None:
            b.cells("spksw-gpio", 7, switch, 0)
        b.end()
    if extra_amp:
        b.begin("aw882xx_smartpa@36")
        b.string("compatible", "awinic,aw882xx_smartpa")
        b.end()
    b.end()
    b.end()
    b.begin("__symbols__")
    b.string("tlmm", "/soc/tlmm@1000")
    b.string("qupv3_se15_i2c",
             "/soc/i2c@9999" if wrong_bus else "/soc/i2c@1200")
    b.end()
    b.end()
    return b.build()


class OEMMondrianAudioFdtTests(unittest.TestCase):
    def test_compiled_oem_audio_source_passes_without_hardware_claim(self):
        evidence = verify_mondrian_audio_fdt(sample_audio())
        self.assertTrue(evidence["oem_board_speaker_gpio_and_i2c_verified"])
        self.assertEqual(sorted(evidence["oem_aw882xx_amplifiers"]), ["0x34", "0x35"])
        self.assertEqual(evidence["oem_aw882xx_amplifiers"]["0x34"]["irq_gpio"], 88)
        self.assertFalse(evidence["audio_driver_abi_verified"])
        self.assertFalse(evidence["physical_audio_tested"])
        self.assertFalse(evidence["production_audio_approved"])

    def test_refuse_incorrect_speaker_i2c_address(self):
        with self.assertRaisesRegex(ValueError, "I2C address"):
            verify_mondrian_audio_fdt(sample_audio(wrong_addr=True))

    def test_refuse_donor_channel_mapping(self):
        with self.assertRaisesRegex(ValueError, "channel mismatch"):
            verify_mondrian_audio_fdt(sample_audio(wrong_channel=True))

    def test_refuse_mismatched_aw_irq(self):
        with self.assertRaisesRegex(ValueError, "GPIO"):
            verify_mondrian_audio_fdt(sample_audio(wrong_irq=True))

    def test_refuse_wrong_tlmm_phandle(self):
        with self.assertRaisesRegex(ValueError, "provider"):
            verify_mondrian_audio_fdt(sample_audio(bad_phandle=True))

    def test_refuse_missing_oem_audio_i2c_controller(self):
        with self.assertRaisesRegex(ValueError, "symbol does not resolve"):
            verify_mondrian_audio_fdt(sample_audio(wrong_bus=True))

    def test_refuse_missing_or_extra_speaker(self):
        for opts in ({"missing_amp": True}, {"extra_amp": True}):
            with self.subTest(opts=opts), self.assertRaisesRegex(ValueError, "exactly two"):
                verify_mondrian_audio_fdt(sample_audio(**opts))

    def test_refuse_wrong_mi2s2_assignment(self):
        with self.assertRaisesRegex(ValueError, "MI2S2 pin"):
            verify_mondrian_audio_fdt(sample_audio(wrong_mi2s=True))


if __name__ == "__main__":
    unittest.main()
