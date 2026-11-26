"""Every pinned OEM copy must be read by the compiled board, never left unused."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_oem_dtbo import preprocessed_sources  # noqa: E402


class PinnedSourcesUsedTests(unittest.TestCase):
    def test_cpp_line_markers_name_stage_relative_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            stage = Path(temp) / "source"
            (stage / "qcom").mkdir(parents=True)
            preprocessed = Path(temp) / "cape.preprocessed.dts"
            preprocessed.write_text(
                f'# 1 "{stage}/qcom/cape.dts"\n'
                f'# 1 "{stage}/qcom/cape.dtsi" 1\n'
                '# 1 "/kernel/include/dt-bindings/gpio/gpio.h" 1\n'
                '# 1 "<built-in>"\n'
                f'# 12 "{stage}/qcom/cape.dtsi" 2\n'
                '/ { model = "x"; };\n')
            self.assertEqual(preprocessed_sources(preprocessed, stage),
                             {"qcom/cape.dts", "qcom/cape.dtsi"})


if __name__ == "__main__":
    unittest.main()
