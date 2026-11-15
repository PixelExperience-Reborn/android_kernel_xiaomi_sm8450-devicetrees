"""Synthetic FDT v17 structural and panel audit, not manufacturer panel data."""
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_xiaomi_panel_evidence import fdt_nodes, panel_evidence_from_fdt  # noqa: E402


class FdtBuilder:
    """Minimal standards-conforming FDT v17 fixture, with synthetic values."""

    def __init__(self):
        self.strings = bytearray()
        self.name_offsets = {}
        self.structure = bytearray()

    def tag(self, number):
        self.structure.extend(struct.pack(">I", number))

    def name(self, value):
        if value not in self.name_offsets:
            self.name_offsets[value] = len(self.strings)
            self.strings.extend(value.encode() + b"\x00")
        return self.name_offsets[value]

    def begin(self, name):
        self.tag(1)
        self.structure.extend(name.encode() + b"\x00")
        self.structure.extend(b"\x00" * (-len(self.structure) % 4))

    def end(self):
        self.tag(2)

    def prop(self, name, value):
        self.tag(3)
        self.structure.extend(struct.pack(">2I", len(value), self.name(name)))
        self.structure.extend(value)
        self.structure.extend(b"\x00" * (-len(self.structure) % 4))

    def string(self, name, value):
        self.prop(name, value.encode() + b"\x00")

    def cells(self, name, *values):
        self.prop(name, struct.pack(">" + "I" * len(values), *values))

    def build(self):
        self.tag(9)
        hdr = 40
        reserve = b"\x00" * 16
        struct_offset = hdr + len(reserve)
        strings_offset = struct_offset + len(self.structure)
        total = strings_offset + len(self.strings)
        header = struct.pack(">10I", 0xD00DFEED, total,
                             struct_offset, strings_offset, hdr,
                             17, 16, 0, len(self.strings),
                             len(self.structure))
        return header + reserve + bytes(self.structure) + bytes(self.strings)


def sample_panel_fdt(*, slice_width=500, outside_hbm=False):
    dt = FdtBuilder()
    dt.begin("")
    dt.begin("soc")
    if outside_hbm:
        dt.begin("other-display")
        dt.prop("mi,local-hbm-enabled", b"")
        dt.end()
    dt.begin("panel@0")
    dt.string("qcom,mdss-dsi-panel-name", "synthetic test panel")
    dt.string("qcom,mdss-dsi-panel-type", "dsi_cmd_mode")
    dt.cells("mi,panel-id", 0x12345678, 0x00000001)
    dt.cells("qcom,mdss-dsi-bl-max-level", 4095)
    dt.prop("mi,local-hbm-enabled", b"")
    dt.prop("qcom,mdss-dsi-on-command", b"\xDE\xAD\xBE\xEF" * 7)
    dt.begin("qcom,mdss-dsi-display-timings")
    dt.begin("timing@0")
    dt.cells("qcom,mdss-dsi-panel-framerate", 60)
    dt.cells("qcom,mdss-dsi-panel-width", 1000)
    dt.cells("qcom,mdss-dsi-panel-height", 2000)
    dt.string("qcom,compression-mode", "dsc")
    dt.cells("qcom,mdss-dsc-version", 0x12)
    dt.cells("qcom,mdss-dsc-slice-width", slice_width)
    dt.cells("qcom,mdss-dsc-slice-height", 32)
    dt.cells("qcom,mdss-dsc-slice-per-pkt", 2)
    dt.cells("qcom,mdss-dsc-bit-per-component", 10)
    dt.cells("qcom,mdss-dsc-bit-per-pixel", 8)
    dt.end()
    dt.end()
    dt.end()
    dt.end()
    dt.end()
    return dt.build()


class ManufacturerPanelEvidenceTests(unittest.TestCase):
    def test_read_numeric_panel_and_dsc_properties_without_command_payload(self):
        blob = sample_panel_fdt()
        output = panel_evidence_from_fdt(blob)
        self.assertEqual(output["panel_candidate_count"], 1)
        panel = output["panel_candidates"][0]
        self.assertEqual(panel["panel_name"], "synthetic test panel")
        self.assertEqual(panel["xiaomi_panel_id_hex"], ["12345678", "00000001"])
        self.assertEqual(panel["backlight_max_level"], 4095)
        self.assertTrue(panel["xiaomi_local_hbm_property_present"])
        self.assertTrue(panel["panel_command_sequences_present"])
        mode = panel["modes"][0]
        self.assertEqual(mode["refresh_hz"], 60)
        self.assertEqual(mode["width_px"], 1000)
        self.assertEqual(mode["dsc_slice_width"], 500)
        self.assertEqual(mode["dsc_slice_height"], 32)
        self.assertEqual(mode["dsc_version"], 0x12)
        self.assertTrue(mode["basic_geometry_and_dsc_valid"])
        self.assertFalse(mode["physical_panel_validated"])
        self.assertFalse(output["production_panel_dts_approved"])
        self.assertNotIn("deadbeef", json.dumps(output).lower())

    def test_invalid_zero_slice_is_rejected_without_division(self):
        output = panel_evidence_from_fdt(sample_panel_fdt(slice_width=0))
        self.assertFalse(output["panel_candidates"][0]["modes"][0][
            "basic_geometry_and_dsc_valid"])

    def test_invalid_nondivisible_slice_is_rejected(self):
        output = panel_evidence_from_fdt(sample_panel_fdt(slice_width=499))
        self.assertFalse(output["panel_candidates"][0]["modes"][0][
            "basic_geometry_and_dsc_valid"])

    def test_empty_boolean_property_from_different_node_is_not_inherited(self):
        dt = FdtBuilder()
        dt.begin("")
        dt.begin("other")
        dt.prop("mi,local-hbm-enabled", b"")
        dt.end()
        dt.begin("panel@0")
        dt.string("qcom,mdss-dsi-panel-name", "my panel")
        dt.end()
        dt.end()
        result = panel_evidence_from_fdt(dt.build())
        self.assertFalse(result["panel_candidates"][0][
            "xiaomi_local_hbm_property_present"])

    def test_root_xiaomi_board_identity_is_reported_without_claiming_match(self):
        builder = FdtBuilder()
        builder.begin("")
        builder.prop("compatible", b"qcom,cape-mtp\x00qcom,cape\x00")
        builder.cells("qcom,msm-id", 530, 0x10000, 531, 0x10000)
        builder.cells("qcom,board-id", 0x10008, 0)
        builder.cells("xiaomi,miboard-id", 0xE, 0)
        builder.begin("other@0")
        builder.cells("xiaomi,miboard-id", 0xDEADBEEF)
        builder.end()
        builder.end()
        output = panel_evidence_from_fdt(builder.build())
        selectors = output["root_board_signals"]
        self.assertEqual(selectors["root_compatible"],
                         ["qcom,cape-mtp", "qcom,cape"])
        self.assertEqual(selectors["raw_root_id_cells"]["xiaomi,miboard-id"],
                         ["0x0000000e", "0x00000000"])
        self.assertEqual(selectors["raw_root_id_cells"]["qcom,msm-id"],
                         ["0x00000212", "0x00010000",
                          "0x00000213", "0x00010000"])
        self.assertFalse(selectors["stock_board_revision_verified"])
        self.assertEqual(output["panel_candidate_count"], 0)

    def test_non_u32_or_oversize_board_selector_is_not_misinterpreted(self):
        builder = FdtBuilder()
        builder.begin("")
        builder.prop("xiaomi,miboard-id", b"bad")
        builder.end()
        selectors = panel_evidence_from_fdt(
            builder.build())["root_board_signals"]
        self.assertNotIn("xiaomi,miboard-id", selectors["raw_root_id_cells"])
        self.assertFalse(selectors["stock_board_revision_verified"])

    def test_non_panel_fdt_does_not_claim_m11a(self):
        dt = FdtBuilder()
        dt.begin("")
        dt.begin("fingerprint")
        dt.string("compatible", "goodix,fingerprint")
        dt.end()
        dt.end()
        result = panel_evidence_from_fdt(dt.build())
        self.assertEqual(result["panel_candidate_count"], 0)
        self.assertFalse(result["production_panel_dts_approved"])

    def test_reject_wrong_fdt_root(self):
        dt = FdtBuilder()
        dt.begin("bad-root")
        dt.end()
        with self.assertRaisesRegex(ValueError, "root"):
            fdt_nodes(dt.build())

    def test_reject_corrupt_property_strings_offset(self):
        dt = FdtBuilder()
        dt.begin("")
        dt.cells("dummy", 7)
        dt.end()
        raw = bytearray(dt.build())
        # FDT v17: header 40 + reserve-map 16 + root begin/name 8
        struct.pack_into(">I", raw, 56 + 8 + 8, 0x7FFFFFFF)
        with self.assertRaisesRegex(ValueError, "extends beyond block"):
            fdt_nodes(raw)

    def test_reject_truncated_structure_block(self):
        raw = bytearray(sample_panel_fdt())
        struct.pack_into(">I", raw, 36, 0xFFFFFFF0)
        # The existing FDT header validator may reject this before the
        # new structure parser sees it. Both paths must fail closed.
        with self.assertRaisesRegex(
                ValueError, "overflows totalsize|outside aligned bounds"):
            fdt_nodes(raw)

    def test_reject_corrupt_fdt_property_padding(self):
        dt = FdtBuilder()
        dt.begin("")
        dt.prop("short", b"\x01")
        dt.end()
        raw = bytearray(dt.build())
        # Header 40, reserve 16, root begin/empty name = 8,
        # property token/length/nameoff = 12, then 1-byte value and padding.
        raw[56 + 8 + 12 + 1] = 0xA5
        with self.assertRaisesRegex(ValueError, "property padding"):
            fdt_nodes(raw)

    def test_reject_invalid_token(self):
        dt = FdtBuilder()
        dt.begin("")
        dt.end()
        raw = bytearray(dt.build())
        struct.pack_into(">I", raw, 56, 0x99)
        with self.assertRaisesRegex(ValueError, "invalid FDT token"):
            fdt_nodes(raw)


if __name__ == "__main__":
    unittest.main()
