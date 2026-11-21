"""Preserve exact kernel provenance for OEM Cape/SM8475 DT compilation."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "dt_compile", ROOT / "tools/build_oem_dtbo.py"
)
dt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dt)

OEM = "2466406b9beac724960b0c88e6e794421d0466e7"
COHERENT = "69c3911404debdfab1eb484aaa626b319b9d93d7"


class KernelRevisionProvenanceTests(unittest.TestCase):
    def test_oem_and_coherent_sha_must_match_checked_out_source(self):
        for sha in (OEM, COHERENT):
            with self.subTest(sha=sha), patch.object(
                    dt.subprocess, "check_output", return_value=sha + "\n"):
                self.assertEqual(dt.verify_kernel_revision(Path("/fake/kernel"), sha), sha)

    def test_wrong_revision_is_rejected(self):
        with patch.object(dt.subprocess, "check_output", return_value=OEM + "\n"):
            with self.assertRaisesRegex(ValueError, "Kernel commit mismatch"):
                dt.verify_kernel_revision(Path("/fake/kernel"), COHERENT)

    def test_symbolic_or_malformed_revision_is_rejected(self):
        for value in ("HEAD", "a" * 39, "G" * 40, ""):
            with self.subTest(ref=value), patch.object(
                    dt.subprocess, "check_output") as mocked:
                with self.assertRaisesRegex(ValueError, "40-hex SHA"):
                    dt.verify_kernel_revision(Path("/fake/kernel"), value)
                mocked.assert_not_called()


if __name__ == "__main__":
    unittest.main()
