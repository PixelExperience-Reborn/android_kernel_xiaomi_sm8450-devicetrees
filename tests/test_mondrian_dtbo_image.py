"""dtbo.img layout and overlay source joining of tools/build_mondrian_dtbo.py."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_mondrian_dtbo import dtbo_image, strip_source  # noqa: E402


class MondrianDtboImageTests(unittest.TestCase):
    def test_one_entry_android_dtbo_v0_as_stock(self):
        with tempfile.TemporaryDirectory() as temp:
            overlay = Path(temp) / "mondrian.dtbo"
            overlay.write_bytes(b"\xd0\x0d\xfe\xed" + b"\0" * 60)
            image = Path(temp) / "dtbo.img"
            dtbo_image(overlay, image)
            data = image.read_bytes()
            magic, total, hsz, esz, count, eoff, page, version = struct.unpack(">8I", data[:32])
            self.assertEqual((magic, hsz, esz, count, eoff, page, version),
                             (0xD7B7AB1E, 32, 32, 1, 32, 4096, 0))
            self.assertEqual(total, len(data))
            size, offset, *ids = struct.unpack(">8I", data[32:64])
            self.assertEqual(ids, [0] * 6)
            self.assertEqual(data[offset:offset + size], overlay.read_bytes())

    def test_sources_lose_headers_and_line_markers_only(self):
        text = '# 1 "a.dts"\n/dts-v1/;\n/plugin/;\n&soc {\n\tx = <1>;\n};\n'
        self.assertEqual(strip_source(text), "\n\n&soc {\n\tx = <1>;\n};\n")


if __name__ == "__main__":
    unittest.main()
