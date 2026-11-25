"""Check safe temporary normalization of *compiled*, not stock Xiaomi FDTs."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_oem_dtbo import canonicalize_generated_overlay_fdt


class CompiledOverlayCanonicalizationTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.raw = self.root / "actual-merged.dtb"
        self.copy = self.root / "inspection-only.dtb"
        self.raw_bytes = b"OEM-original-binary-not-flashable" * 10
        self.canonical_bytes = b"OEM-canonical-for-inspection-only" * 10
        self.raw.write_bytes(self.raw_bytes)

    def _mock_dtc(self, args, stdout=None):
        self.assertEqual(args[:6],
                         ["dtc", "-I", "dtb", "-O", "dtb", "-o"])
        self.assertEqual(args[6], self.copy)
        self.assertEqual(args[7], self.raw)
        self.copy.write_bytes(self.canonical_bytes)

    def test_full_dts_equivalence_and_original_byte_preservation(self):
        with patch("build_oem_dtbo.run", side_effect=self._mock_dtc):
            with patch("build_oem_dtbo.subprocess.check_output",
                       side_effect=[b"/dts-v1/; all properties\n",
                                    b"/dts-v1/; all properties\n"]) as commands:
                evidence = canonicalize_generated_overlay_fdt(
                    self.raw, self.copy)
        self.assertEqual(self.raw.read_bytes(), self.raw_bytes)
        self.assertEqual(self.copy.read_bytes(), self.canonical_bytes)
        self.assertTrue(evidence[
            "complete_original_and_canonical_dts_identical"])
        self.assertTrue(evidence[
            "canonical_copy_used_only_for_static_pmic_inspection"])
        self.assertTrue(evidence["original_merged_dtb_not_replaced"])
        self.assertEqual(
            evidence["original_merged_dtb_sha256"],
            hashlib.sha256(self.raw_bytes).hexdigest())
        self.assertEqual(
            evidence["inspection_only_canonical_dtb_sha256"],
            hashlib.sha256(self.canonical_bytes).hexdigest())
        self.assertEqual(commands.call_count, 2)
        self.assertEqual(
            commands.call_args_list[0].args[0],
            ["dtc", "-I", "dtb", "-O", "dts", str(self.raw)])
        self.assertEqual(
            commands.call_args_list[1].args[0],
            ["dtc", "-I", "dtb", "-O", "dts", str(self.copy)])

    def test_changed_property_dts_must_fail(self):
        with patch("build_oem_dtbo.run", side_effect=self._mock_dtc):
            with patch("build_oem_dtbo.subprocess.check_output",
                       side_effect=[b"camera-sensor=safe",
                                    b"camera-sensor=unapproved"]):
                with self.assertRaisesRegex(
                        RuntimeError, "changed OEM DT semantics"):
                    canonicalize_generated_overlay_fdt(self.raw, self.copy)
        self.assertEqual(self.raw.read_bytes(), self.raw_bytes)

    def test_existing_inspection_target_must_not_be_overwritten(self):
        self.copy.write_bytes(b"valuable-existing-image")
        with self.assertRaisesRegex(RuntimeError, "refusing to overwrite"):
            canonicalize_generated_overlay_fdt(self.raw, self.copy)
        self.assertEqual(self.copy.read_bytes(), b"valuable-existing-image")

    def test_missing_output_and_truncated_input_fail_closed(self):
        self.raw.write_bytes(b"too-short")
        with self.assertRaisesRegex(RuntimeError, "truncated"):
            canonicalize_generated_overlay_fdt(self.raw, self.copy)
        self.raw.write_bytes(self.raw_bytes)
        with patch("build_oem_dtbo.run"):
            with self.assertRaisesRegex(RuntimeError, "failed to produce"):
                canonicalize_generated_overlay_fdt(self.raw, self.copy)


if __name__ == "__main__":
    unittest.main()
